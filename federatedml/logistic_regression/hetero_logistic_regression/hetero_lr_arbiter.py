#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import numpy as np
from arch.api import federation
from arch.api.utils import log_utils
from federatedml.logistic_regression.base_logistic_regression import BaseLogisticRegression
from federatedml.optim import Optimizer
from federatedml.optim.convergence import DiffConverge
from federatedml.optim.federated_aggregator import HeteroFederatedAggregator
from federatedml.util import HeteroLRTransferVariable
from federatedml.util import consts

LOGGER = log_utils.getLogger()


class HeteroLRArbiter(BaseLogisticRegression):
    def __init__(self, logistic_params):
        super(HeteroLRArbiter, self).__init__(logistic_params)
        self.converge_func = DiffConverge(logistic_params.eps)

        # attribute
        self.pre_loss = None
        self.batch_num = None
        self.transfer_variable = HeteroLRTransferVariable()
        self.optimizer = Optimizer(logistic_params.learning_rate, logistic_params.optimizer)
        self.key_length = logistic_params.encrypt_param.key_length

    def fit(self, data_instance=None):
        # Generate encrypt keys
        self.encrypt_operator.generate_key(self.key_length)
        public_key = self.encrypt_operator.get_public_key()
        public_key = public_key
        LOGGER.info("public_key:{}".format(public_key))
        federation.remote(public_key,
                          name=self.transfer_variable.paillier_pubkey.name,
                          tag=self.transfer_variable.generate_transferid(self.transfer_variable.paillier_pubkey),
                          role=consts.HOST,
                          idx=0)
        LOGGER.info("remote public_key to host")

        federation.remote(public_key,
                          name=self.transfer_variable.paillier_pubkey.name,
                          tag=self.transfer_variable.generate_transferid(self.transfer_variable.paillier_pubkey),
                          role=consts.GUEST,
                          idx=0)
        LOGGER.info("remote public_key to guest")

        batch_info = federation.get(name=self.transfer_variable.batch_info.name,
                                    tag=self.transfer_variable.generate_transferid(self.transfer_variable.batch_info),
                                    idx=0)
        LOGGER.info("Get batch_info from guest:{}".format(batch_info))
        self.batch_num = batch_info["batch_num"]

        is_stop = False
        self.n_iter_ = 0
        while self.n_iter_ < self.max_iter:
            LOGGER.info("iter:{}".format(self.n_iter_))
            batch_index = 0
            while batch_index < self.batch_num:
                LOGGER.info("batch:{}".format(batch_index))
                host_gradient = federation.get(name=self.transfer_variable.host_gradient.name,
                                               tag=self.transfer_variable.generate_transferid(
                                                   self.transfer_variable.host_gradient, self.n_iter_, batch_index),
                                               idx=0)
                LOGGER.info("Get host_gradient from Host")
                guest_gradient = federation.get(name=self.transfer_variable.guest_gradient.name,
                                                tag=self.transfer_variable.generate_transferid(
                                                    self.transfer_variable.guest_gradient, self.n_iter_, batch_index),
                                                idx=0)
                LOGGER.info("Get guest_gradient from Guest")

                # aggregate gradient
                host_gradient, guest_gradient = np.array(host_gradient), np.array(guest_gradient)
                gradient = np.hstack((np.array(host_gradient), np.array(guest_gradient)))
                # decrypt gradient
                for i in range(gradient.shape[0]):
                    gradient[i] = self.encrypt_operator.decrypt(gradient[i])

                # optimization
                optim_gradient = self.optimizer.apply_gradients(gradient)
                # separate optim_gradient according gradient size of Host and Guest
                separate_optim_gradient = HeteroFederatedAggregator.separate(optim_gradient,
                                                                             [host_gradient.shape[0],
                                                                              guest_gradient.shape[0]])
                host_optim_gradient = separate_optim_gradient[0]
                guest_optim_gradient = separate_optim_gradient[1]

                federation.remote(host_optim_gradient,
                                  name=self.transfer_variable.host_optim_gradient.name,
                                  tag=self.transfer_variable.generate_transferid(
                                      self.transfer_variable.host_optim_gradient,
                                      self.n_iter_,
                                      batch_index),
                                  role=consts.HOST,
                                  idx=0)
                LOGGER.info("Remote host_optim_gradient to Host")

                federation.remote(guest_optim_gradient,
                                  name=self.transfer_variable.guest_optim_gradient.name,
                                  tag=self.transfer_variable.generate_transferid(
                                      self.transfer_variable.guest_optim_gradient,
                                      self.n_iter_,
                                      batch_index),
                                  role=consts.GUEST,
                                  idx=0)
                LOGGER.info("Remote guest_optim_gradient to Guest")

                loss = federation.get(name=self.transfer_variable.loss.name,
                                      tag=self.transfer_variable.generate_transferid(
                                          self.transfer_variable.loss, self.n_iter_, batch_index),
                                      idx=0)

                de_loss = self.encrypt_operator.decrypt(loss)
                LOGGER.info("Get loss from guest:{}".format(de_loss))
                # if converge
                if self.converge_func.is_converge(de_loss):
                    is_stop = True

                federation.remote(is_stop,
                                  name=self.transfer_variable.is_stopped.name,
                                  tag=self.transfer_variable.generate_transferid(self.transfer_variable.is_stopped,
                                                                                 self.n_iter_,
                                                                                 batch_index),
                                  role=consts.HOST,
                                  idx=0)
                LOGGER.info("Remote is_stop to guest:{}".format(is_stop))

                federation.remote(is_stop,
                                  name=self.transfer_variable.is_stopped.name,
                                  tag=self.transfer_variable.generate_transferid(self.transfer_variable.is_stopped,
                                                                                 self.n_iter_,
                                                                                 batch_index),
                                  role=consts.GUEST,
                                  idx=0)
                LOGGER.info("Remote is_stop to guest:".format(is_stop))

                batch_index += 1
                if is_stop:
                    LOGGER.info("Model is converged, iter:{}".format(self.n_iter_))
                    break

            self.n_iter_ += 1
            if is_stop:
                break

        LOGGER.info("Reach max iter {}, train model finish!".format(self.max_iter))
