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

# =============================================================================
# Boostring Tree
# =============================================================================


class BoostingTree(object):
    def __init__(self, boostingtree_param):
        self.tree_param = boostingtree_param.tree_param
        self.task_type = boostingtree_param.task_type
        self.loss_type = boostingtree_param.loss_type
        self.learning_rate = boostingtree_param.learning_rate
        self.num_trees = boostingtree_param.num_trees
        self.subsample_feature_rate = boostingtree_param.subsample_feature_rate
        self.n_iter_no_change = boostingtree_param.n_iter_no_change
        self.encrypt_param = boostingtree_param.encrypt_param
        self.tol = boostingtree_param.tol
        self.quantile_method = boostingtree_param.quantile_method
        self.bin_num = boostingtree_param.bin_num
        self.bin_gap = boostingtree_param.bin_gap
        self.bin_sample_num = boostingtree_param.bin_sample_num

    def fit(self, data_inst):
        pass

    def predict(self, data_inst, threshold=0.5):
        pass

    def predict_proba(self, data_inst):
        pass

    def load_model(self):
        pass

    def save_mode(self):
        pass
