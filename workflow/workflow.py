#!/usr/bin/env python    
# -*- coding: utf-8 -*- 

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
################################################################################
#
#
################################################################################

import argparse
import json
from arch.api.utils import log_utils

import numpy as np

from arch.api import eggroll
from arch.api import federation
from federatedml.model_selection import KFold
from federatedml.param import WorkFlowParam
from federatedml.util import ParamExtract, DenseFeatureReader, SparseFeatureReader
from federatedml.util import consts
from federatedml.util.transfer_variable import HeteroWorkFlowTransferVariable

LOGGER = log_utils.getLogger()


class WorkFlow(object):
    def __init__(self):
        # self._initialize(config_path)
        self.model = None
        self.role = None
        self.mode = None
        self.workflow_param = None
        self.intersection = None

    def _initialize(self, config_path):
        self._initialize_role_and_mode()
        self._initialize_model(config_path)
        self._initialize_workflow_param(config_path)

    def _initialize_role_and_mode(self):
        self.role = consts.GUEST
        self.mode = consts.HETERO

    def _initialize_intersect(self, config):
        raise NotImplementedError("method init must be define")

    def _initialize_model(self, config):
        raise NotImplementedError("method init must be define")
        """
        use case

        secureboost_param = SecureboostTreeParam()
        self.secureboost_param = param_extract.ParamExtract.parse_param_from_config(secureboost_param, config_path)
        self.model = SecureBoostTreeModel(self.secureboost_param)
        """

    def _synchronous_data(self, data_instance, flowid, data_application=None):
        if data_application is None:
            LOGGER.warning("not data_application!")
            return

        transfer_variable = HeteroWorkFlowTransferVariable()
        if data_application == consts.TRAIN_DATA:
            transfer_id = transfer_variable.train_data
        elif data_application == consts.TEST_DATA:
            transfer_id = transfer_variable.test_data
        else:
            LOGGER.warning("data_application error!")
            return

        if self.role == consts.GUEST:
            data_sid = data_instance.mapValues(lambda v: 1)

            federation.remote(data_sid,
                              name=transfer_id.name,
                              tag=transfer_variable.generate_transferid(transfer_id, flowid),
                              role=consts.HOST,
                              idx=0)
            LOGGER.info("remote {} to host".format(data_application))
            return None
        elif self.role == consts.HOST:
            data_sid = federation.get(name=transfer_id.name,
                                      tag=transfer_variable.generate_transferid(transfer_id, flowid),
                                      idx=0)

            LOGGER.info("get {} from guest".format(data_application))
            join_data_insts = data_sid.join(data_instance, lambda s, d: d)
            return join_data_insts

    def _initialize_workflow_param(self, config_path):
        workflow_param = WorkFlowParam()
        self.workflow_param = ParamExtract.parse_param_from_config(workflow_param, config_path)

    def _init_logger(self, LOGGER_path):
        pass
        # LOGGER.basicConfig(level=LOGGER.DEBUG,
        #                    format='%(asctime)s %(levelname)s %(message)s',
        #                    datefmt='%a, %d %b %Y %H:%M:%S',
        #                    filename=LOGGER_path,
        #                    filemode='w')

    def train(self, train_data, validation_data=None):
        LOGGER.debug("Enter train function")
        self.model.fit(train_data)
        self.save_model()
        LOGGER.debug("finish saving, self role: {}".format(self.role))
        if self.role == consts.GUEST or self.role == consts.HOST or \
                self.mode == consts.HOMO:
            eval_result = {}
            LOGGER.debug("predicting...")
            # train_pred = self.model.predict(train_data)
            predict_result = self.model.predict(train_data,
                                                self.workflow_param.predict_param)
            LOGGER.debug("evaluating...")
            train_eval = self.evaluate(predict_result)
            eval_result[consts.TRAIN_EVALUATE] = train_eval
            if validation_data is not None:
                # val_pred = self.model.predict(validation_data)
                val_pred = self.model.predict(validation_data,
                                                    self.workflow_param.predict_param)
                val_eval = self.evaluate(val_pred)
                eval_result[consts.VALIDATE_EVALUATE] = val_eval
            LOGGER.info("{} eval_result: {}".format(self.role, eval_result))
            self.save_eval_result(eval_result)

    def save_eval_result(self, eval_data):
        eggroll.parallelize([eval_data],
                            include_key=False,
                            name=self.workflow_param.evaluation_output_table,
                            namespace=self.workflow_param.evaluation_output_namespace,
                            error_if_exist=False,
                            persistent=True
                            )

    def predict(self, data_instance):
        # self.load_model()
        # LOGGER.debug("predict data size: {}".format(data_instance.count()))
        predict_result = self.model.predict(data_instance,
                                            self.workflow_param.predict_param)

        if self.role == consts.GUEST:
            self.save_predict_result(predict_result)
            if self.workflow_param.dataio_param.with_label:
                eval_result = self.evaluate(predict_result)
                LOGGER.info("eval_result: {}".format(eval_result))
                self.save_eval_result(eval_result)
        if self.mode == consts.HOMO and self.role == consts.HOST:
            self.save_predict_result(predict_result)

        if not predict_result:
            return None
        LOGGER.debug("predict result: {}".format(predict_result))
        if predict_result.count() > 10:
            local_predict = predict_result.collect()
            n = 0
            while n < 10:
                result = local_predict.__next__()
                LOGGER.debug("predict result: {}".format(result))
                n += 1

        return predict_result

    def intersect(self, data_instance):
        raise NotImplementedError("method init must be define")

    def cross_validation(self, data_instance):
        if self.mode == consts.HETERO:
            cv_results = self.hetero_cross_validation(data_instance)
        elif self.mode == consts.HOMO:
            cv_results = self.homo_cross_validation(data_instance)
        else:
            cv_results = {}

        if self.role == consts.GUEST or (self.role == consts.HOST and self.mode == consts.HOMO):
            format_cv_result = {}
            for eval_result in cv_results:
                for eval_name, eval_r in eval_result.items():
                    if not isinstance(eval_r, list):
                        if eval_name not in format_cv_result:
                            format_cv_result[eval_name] = []
                        format_cv_result[eval_name].append(eval_r)
                    else:
                        for e_r in eval_r:
                            e_name = "{}_thres_{}".format(eval_name, e_r[0])
                            if e_name not in format_cv_result:
                                format_cv_result[e_name] = []
                            format_cv_result[e_name].append(e_r[1])

            for eval_name, eva_result_list in format_cv_result.items():
                mean_value = np.around(np.mean(eva_result_list), 4)
                std_value = np.around(np.std(eva_result_list), 4)
                LOGGER.info("evaluate name: {}, mean: {}, std: {}".format(eval_name, mean_value, std_value))

    def hetero_cross_validation(self, data_instance):
        n_splits = self.workflow_param.n_splits

        if self.role == consts.GUEST:
            LOGGER.info("In hetero cross_validation Guest")
            k_fold_obj = KFold(n_splits=n_splits)
            kfold_data_generator = k_fold_obj.split(data_instance)
            flowid = 0
            cv_results = []
            for train_data, test_data in kfold_data_generator:
                LOGGER.info("flowid:{}".format(flowid))
                self._synchronous_data(train_data, flowid, consts.TRAIN_DATA)
                LOGGER.info("synchronous train data")
                self._synchronous_data(test_data, flowid, consts.TEST_DATA)
                LOGGER.info("synchronous test data")

                self.model.set_flowid(flowid)
                self.model.fit(train_data)
                pred_res = self.model.predict(test_data, self.workflow_param.predict_param)
                evaluation_results = self.evaluate(pred_res)
                cv_results.append(evaluation_results)
                flowid += 1
                LOGGER.info("cv" + str(flowid) + " evaluation:" + str(evaluation_results))
                self._initialize_model(self.config_path)

            LOGGER.info("total cv evaluation:{}".format(cv_results))
            return cv_results

        elif self.role == consts.HOST:
            LOGGER.info("In hetero cross_validation Host")
            for flowid in range(n_splits):
                LOGGER.info("flowid:{}".format(flowid))
                train_data = self._synchronous_data(data_instance, flowid, consts.TRAIN_DATA)
                LOGGER.info("synchronous train data")
                test_data = self._synchronous_data(data_instance, flowid, consts.TEST_DATA)
                LOGGER.info("synchronous test data")

                self.model.set_flowid(flowid)
                self.model.fit(train_data)
                self.model.predict(test_data)
                flowid += 1
                self._initialize_model(self.config_path)

        elif self.role == consts.ARBITER:
            LOGGER.info("In hetero cross_validation Arbiter")
            for flowid in range(n_splits):
                LOGGER.info("flowid:{}".format(flowid))
                self.model.set_flowid(flowid)
                self.model.fit()
                flowid += 1
                self._initialize_model(self.config_path)

    def load_eval_result(self):
        eval_data = eggroll.table(
            name=self.workflow_param.evaluation_output_table,
            namespace=self.workflow_param.evaluation_output_namespace,
        )
        LOGGER.debug("Evaluate result loaded: {}".format(eval_data))
        return eval_data

    def homo_cross_validation(self, data_instance):
        n_splits = self.workflow_param.n_splits
        k_fold_obj = KFold(n_splits=n_splits)
        kfold_data_generator = k_fold_obj.split(data_instance)
        cv_result = []
        flowid = 0
        LOGGER.info("Doing Homo cross validation")
        for train_data, test_data in kfold_data_generator:
            LOGGER.info("This is the {}th fold".format(flowid))
            self.model.set_flowid(flowid)
            self.model.fit(train_data)
            # self.save_model()
            predict_result = self.model.predict(test_data, self.workflow_param.predict_param)
            flowid += 1

            eval_result = self.evaluate(predict_result)
            cv_result.append(eval_result)
            self._initialize_model(self.config_path)

        return cv_result

    def save_model(self):
        LOGGER.debug("save model, model table: {}, model namespace: {}".format(
            self.workflow_param.model_table, self.workflow_param.model_namespace))
        self.model.save_model(self.workflow_param.model_table, self.workflow_param.model_namespace)

    def load_model(self):
        self.model.load_model(self.workflow_param.model_table, self.workflow_param.model_namespace)

    def save_predict_result(self, predict_result):
        predict_result.save_as(self.workflow_param.predict_output_table, self.workflow_param.predict_output_namespace)

    def save_intersect_result(self, intersect_result):
        LOGGER.info("Save intersect results to name:{}, namespace:{}".format(
            self.workflow_param.intersect_data_output_table, self.workflow_param.intersect_data_output_namespace))
        intersect_result.save_as(self.workflow_param.intersect_data_output_table,
                                 self.workflow_param.intersect_data_output_namespace)

    def evaluate(self, eval_data):
        if eval_data is None:
            LOGGER.info("not eval_data!")
            return None

        eval_data_local = eval_data.collect()
        labels = []
        pred_prob = []
        pred_labels = []
        for data in eval_data_local:
            labels.append(data[1][0])
            pred_prob.append(data[1][1])
            pred_labels.append(data[1][2])

        labels = np.array(labels)
        pred_prob = np.array(pred_prob)
        pred_labels = np.array(pred_labels)

        evaluation_result = self.model.evaluate(labels, pred_prob, pred_labels,
                                                evaluate_param=self.workflow_param.evaluate_param)
        return evaluation_result

    def gen_data_instance(self, table, namespace):
        reader = None
        if self.workflow_param.dataio_param.input_format == "dense":
            reader = DenseFeatureReader(self.workflow_param.dataio_param)
        else:
            reader = SparseFeatureReader(self.workflow_param.dataio_param)
        data_instance = reader.read_data(table, namespace)
        return data_instance

    def _init_argument(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', '--config', required=True, type=str, help="Specify a config json file path")
        parser.add_argument('-j', '--job_id', type=str, required=True, help="Specify the job id")
        # parser.add_argument('-p', '--party_id', type=str, required=True, help="Specify the party id")
        # parser.add_argument('-l', '--LOGGER_path', type=str, required=True, help="Specify the LOGGER path")
        args = parser.parse_args()
        config_path = args.config
        self.config_path = config_path
        if not args.config:
            LOGGER.error("Config File should be provided")
            exit(-100)
        job_id = args.job_id
        # party_id = args.party_id
        # LOGGER_path = args.LOGGER_path
        # self._init_LOGGER(LOGGER_path)
        self._initialize(config_path)
        with open(config_path) as conf_f:
            runtime_json = json.load(conf_f)
        eggroll.init(job_id, self.workflow_param.work_mode)
        LOGGER.debug("The job id is {}".format(job_id))
        federation.init(job_id, runtime_json)
        LOGGER.debug("Finish eggroll and federation init")

    def run(self):
        self._init_argument()

        if self.workflow_param.method == "train":
            LOGGER.debug("In running function, enter train method")
            train_data_instance = None
            predict_data_instance = None
            if self.role != consts.ARBITER:
                LOGGER.debug("Input table:{}, input namesapce: {}".format(
                    self.workflow_param.train_input_table, self.workflow_param.train_input_namespace
                ))
                train_data_instance = self.gen_data_instance(self.workflow_param.train_input_table,
                                                             self.workflow_param.train_input_namespace)
                # LOGGER.debug("train_data_instance count:{}".format(train_data_instance.count()))
                LOGGER.debug("gen_data_finish")
                if self.workflow_param.predict_input_table is not None and self.workflow_param.predict_input_namespace is not None:
                    LOGGER.debug("Input table:{}, input namesapce: {}".format(
                        self.workflow_param.predict_input_table, self.workflow_param.predict_input_namespace
                    ))
                    predict_data_instance = self.gen_data_instance(self.workflow_param.predict_input_table,
                                                                   self.workflow_param.predict_input_namespace)

            self.train(train_data_instance, validation_data=predict_data_instance)

        elif self.workflow_param.method == "predict":
            data_instance = self.gen_data_instance(self.workflow_param.predict_input_table,
                                                   self.workflow_param.predict_input_namespace)
            self.load_model()
            self.predict(data_instance)

        elif self.workflow_param.method == "intersect":
            LOGGER.debug("[Intersect]Input table:{}, input namesapce: {}".format(
                self.workflow_param.data_input_table,
                self.workflow_param.data_input_namespace
            ))
            data_instance = self.gen_data_instance(self.workflow_param.data_input_table,
                                                   self.workflow_param.data_input_namespace)
            # LOGGER.debug("[Intersect] data_instance count:{}".format(data_instance.count()))
            self.intersect(data_instance)

        elif self.workflow_param.method == "cross_validation":
            data_instance = self.gen_data_instance(self.workflow_param.data_input_table,
                                                   self.workflow_param.data_input_namespace)
            self.cross_validation(data_instance)
        # elif self.workflow_param.method == 'test_methods':
        #     print("This is a test method, Start workflow success!")
        #     LOGGER.debug("Testing LOGGER function")
        else:
            raise TypeError("method %s is not support yet" % (self.workflow_param.method))


if __name__ == "__main__":
    pass
    """
    method_list
    param_init
    method.run(params)
    """
