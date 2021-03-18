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
from federatedml.model_selection import MiniBatch
from federatedml.optim import activation
from federatedml.optim.gradient import HeteroLogisticGradient
from federatedml.util import consts
from federatedml.util.transfer_variable import HeteroLRTransferVariable

LOGGER = log_utils.getLogger()


class HeteroLRGuest(BaseLogisticRegression):
    def __init__(self, logistic_params):
        super(HeteroLRGuest, self).__init__(logistic_params)
        self.transfer_variable = HeteroLRTransferVariable()
        self.data_batch_count = []

        self.wx = None
        self.guest_forward = None

    def compute_forward(self, data_instances, coef_, intercept_):
        self.wx = self.compute_wx(data_instances, coef_, intercept_)
        encrypt_operator = self.encrypt_operator
        self.guest_forward = self.wx.mapValues(
            lambda v: (encrypt_operator.encrypt(v), encrypt_operator.encrypt(np.square(v)), v))

    def aggregate_forward(self, host_forward):
        aggregate_forward_res = self.guest_forward.join(host_forward,
                                                        lambda g, h: (g[0] + h[0], g[1] + h[1] + 2 * g[2] * h[0]))
        return aggregate_forward_res

    @staticmethod
    def load_data(data_instance):
        if data_instance.label != 1:
            data_instance.label = -1
        return data_instance

    def fit(self, data_instances):
        LOGGER.info("Enter hetero_lr_guest fit")
        data_instances = data_instances.mapValues(HeteroLRGuest.load_data)

        public_key = federation.get(name=self.transfer_variable.paillier_pubkey.name,
                                    tag=self.transfer_variable.generate_transferid(
                                        self.transfer_variable.paillier_pubkey),
                                    idx=0)
        LOGGER.info("Get public_key from arbiter:{}".format(public_key))
        self.encrypt_operator.set_public_key(public_key)

        LOGGER.info("Generate mini-batch from input data")
        mini_batch_obj = MiniBatch(data_instances, batch_size=self.batch_size)
        batch_info = {"batch_size": self.batch_size, "batch_num": mini_batch_obj.batch_nums}
        LOGGER.info("batch_info:" + str(batch_info))
        federation.remote(batch_info,
                          name=self.transfer_variable.batch_info.name,
                          tag=self.transfer_variable.generate_transferid(self.transfer_variable.batch_info),
                          role=consts.HOST,
                          idx=0)
        LOGGER.info("Remote batch_info to Host")
        federation.remote(batch_info,
                          name=self.transfer_variable.batch_info.name,
                          tag=self.transfer_variable.generate_transferid(self.transfer_variable.batch_info),
                          role=consts.ARBITER,
                          idx=0)
        LOGGER.info("Remote batch_info to Arbiter")

        LOGGER.info("Start initialize model.")
        LOGGER.info("fit_intercept:{}".format(self.init_param_obj.fit_intercept))
        model_shape = self.get_features_shape(data_instances)
        weight = self.initializer.init_model(model_shape, init_params=self.init_param_obj)
        if self.init_param_obj.fit_intercept is True:
            self.coef_ = weight[:-1]
            self.intercept_ = weight[-1]
        else:
            self.coef_ = weight

        is_stopped = False
        is_send_all_batch_index = False
        self.n_iter_ = 0
        while self.n_iter_ < self.max_iter:
            LOGGER.info("iter:{}".format(self.n_iter_))
            batch_data_generator = mini_batch_obj.mini_batch_index_generator(data_inst=data_instances,
                                                                             batch_size=self.batch_size)
            batch_index = 0
            for batch_data_index in batch_data_generator:
                LOGGER.info("batch:{}".format(batch_index))
                if not is_send_all_batch_index:
                    LOGGER.info("remote mini-batch index to Host")
                    federation.remote(batch_data_index,
                                      name=self.transfer_variable.batch_data_index.name,
                                      tag=self.transfer_variable.generate_transferid(
                                          self.transfer_variable.batch_data_index,
                                          self.n_iter_,
                                          batch_index),
                                      role=consts.HOST,
                                      idx=0)
                    if batch_index >= mini_batch_obj.batch_nums - 1:
                        is_send_all_batch_index = True

                # Get mini-batch train data
                batch_data_inst = data_instances.join(batch_data_index, lambda data_inst, index: data_inst)

                # guest/host forward
                self.compute_forward(batch_data_inst, self.coef_, self.intercept_)
                host_forward = federation.get(name=self.transfer_variable.host_forward_dict.name,
                                              tag=self.transfer_variable.generate_transferid(
                                                  self.transfer_variable.host_forward_dict, self.n_iter_, batch_index),
                                              idx=0)
                LOGGER.info("Get host_forward from host")
                aggregate_forward_res = self.aggregate_forward(host_forward)
                en_aggregate_wx = aggregate_forward_res.mapValues(lambda v: v[0])
                en_aggregate_wx_square = aggregate_forward_res.mapValues(lambda v: v[1])

                # compute [[d]]
                if self.gradient_operator is None:
                    self.gradient_operator = HeteroLogisticGradient(self.encrypt_operator)
                fore_gradient = self.gradient_operator.compute_fore_gradient(batch_data_inst, en_aggregate_wx)
                federation.remote(fore_gradient,
                                  name=self.transfer_variable.fore_gradient.name,
                                  tag=self.transfer_variable.generate_transferid(self.transfer_variable.fore_gradient,
                                                                                 self.n_iter_,
                                                                                 batch_index),
                                  role=consts.HOST,
                                  idx=0)
                LOGGER.info("Remote fore_gradient to Host")
                # compute guest gradient and loss
                guest_gradient, loss = self.gradient_operator.compute_gradient_and_loss(batch_data_inst,
                                                                                        fore_gradient,
                                                                                        en_aggregate_wx,
                                                                                        en_aggregate_wx_square,
                                                                                        self.fit_intercept)

                # loss regulation if necessary
                if self.updater is not None:
                    guest_loss_regular = self.updater.loss_norm(self.coef_)
                    loss += self.encrypt_operator.encrypt(guest_loss_regular)

                federation.remote(guest_gradient,
                                  name=self.transfer_variable.guest_gradient.name,
                                  tag=self.transfer_variable.generate_transferid(self.transfer_variable.guest_gradient,
                                                                                 self.n_iter_,
                                                                                 batch_index),
                                  role=consts.ARBITER,
                                  idx=0)
                LOGGER.info("Remote guest_gradient to arbiter")

                optim_guest_gradient = federation.get(name=self.transfer_variable.guest_optim_gradient.name,
                                                      tag=self.transfer_variable.generate_transferid(
                                                          self.transfer_variable.guest_optim_gradient, self.n_iter_,
                                                          batch_index),
                                                      idx=0)
                LOGGER.info("Get optim_guest_gradient from arbiter")

                # update model
                LOGGER.info("update_model")
                self.update_model(optim_guest_gradient)

                # Get loss regulation from Host if regulation is set
                if self.updater is not None:
                    en_host_loss_regular = federation.get(name=self.transfer_variable.host_loss_regular.name,
                                                          tag=self.transfer_variable.generate_transferid(
                                                              self.transfer_variable.host_loss_regular, self.n_iter_,
                                                              batch_index),
                                                          idx=0)
                    LOGGER.info("Get host_loss_regular from Host")
                    loss += en_host_loss_regular

                federation.remote(loss,
                                  name=self.transfer_variable.loss.name,
                                  tag=self.transfer_variable.generate_transferid(self.transfer_variable.loss,
                                                                                 self.n_iter_,
                                                                                 batch_index),
                                  role=consts.ARBITER,
                                  idx=0)
                LOGGER.info("Remote loss to arbiter")

                # is converge of loss in arbiter
                is_stopped = federation.get(name=self.transfer_variable.is_stopped.name,
                                            tag=self.transfer_variable.generate_transferid(
                                                self.transfer_variable.is_stopped, self.n_iter_, batch_index),
                                            idx=0)
                LOGGER.info("Get is_stop flag from arbiter:{}".format(is_stopped))
                batch_index += 1
                if is_stopped:
                    LOGGER.info("Get stop signal from arbiter, model is converged, iter:{}".format(self.n_iter_))
                    break

            self.n_iter_ += 1
            if is_stopped:
                break
        LOGGER.info("Reach max iter {}, train model finish!".format(self.max_iter))

    def predict(self, data_instances, predict_param):
        LOGGER.info("Start predict ...")
        prob_guest = self.compute_wx(data_instances, self.coef_, self.intercept_)
        prob_host = federation.get(name=self.transfer_variable.host_prob.name,
                                   tag=self.transfer_variable.generate_transferid(
                                       self.transfer_variable.host_prob),
                                   idx=0)
        LOGGER.info("Get probability from Host")

        # guest probability
        pred_prob = prob_guest.join(prob_host, lambda g, h: activation.sigmoid(g + h))
        pred_label = self.classified(pred_prob, predict_param.threshold)
        if predict_param.with_proba:
            labels = data_instances.mapValues(lambda v: v.label)
            predict_result = labels.join(pred_prob, lambda label, prob: (label, prob))
        else:
            predict_result = data_instances.mapValues(lambda v: (v.label, None))

        predict_result = predict_result.join(pred_label, lambda r, p: (r[0], r[1], p))
        return predict_result
