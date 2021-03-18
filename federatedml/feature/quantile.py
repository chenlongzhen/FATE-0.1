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
# Quantile
# =============================================================================

from arch.api.utils import log_utils

import numpy as np
import functools
from arch.api import eggroll
from federatedml.feature.sparse_vector import SparseVector
from federatedml.util import consts

LOGGER = log_utils.getLogger()

DEFAULT_BIN_GAP = 1e-6
DEFAULT_BIN_NUM = 32
DEFAULT_BIN_SAMPLE_NUM = 10000


class Quantile(object):
    def __init__(self, params):
        pass

    @staticmethod
    def convert_feature_to_bin(data_instance, method, bin_num=DEFAULT_BIN_NUM,
                               bin_gap=DEFAULT_BIN_GAP, bin_sample_num=DEFAULT_BIN_SAMPLE_NUM,
                               valid_features=None):
        LOGGER.info("begin to fconvert feature to bin")
        bin_split_points = Quantile.find_bin_split_points(data_instance, method, bin_num,
                                                          bin_gap, bin_sample_num, valid_features)

        bin_split_points = np.asarray(bin_split_points)
        bin_sparse_points = Quantile.find_bin_sparse_points(bin_split_points)

        convert_bins = functools.partial(Quantile.convert_instance_to_bin, bin_split_points=bin_split_points)
        data_bin = data_instance.mapValues(convert_bins)

        LOGGER.info("end to fconvert feature to bin")
        return data_bin, bin_split_points, bin_sparse_points

    @staticmethod
    def find_bin_sparse_points(bin_split_points):
        LOGGER.info("find sparse points of bin")
        bin_sparse_points = [0 for i in range(bin_split_points.shape[0])]
        for i in range(bin_split_points.shape[0]):
            if bin_split_points[i].shape[0] == 0:
                continue

            pos = bin_split_points[i].shape[0]
            if bin_split_points[i].shape[0] <= 20:
                for j in range(bin_split_points[i].shape[0]):
                    if bin_split_points[i][j] >= consts.FLOAT_ZERO:
                        pos = j
                        break
            else:
                l = 0
                r = bin_split_points[i].shape[0] - 1
                while l <= r:
                    mid = (l + r) >> 1
                    if bin_split_points[i][mid] >= consts.FLOAT_ZERO:
                        pos = mid
                        r = mid - 1
                    else:
                        l = mid + 1

            bin_sparse_points[i] = pos

        return bin_sparse_points

    @staticmethod
    def find_bin_split_points(data_instance, method, bin_num=DEFAULT_BIN_NUM,
                              bin_gap=DEFAULT_BIN_GAP, bin_sample_num=DEFAULT_BIN_SAMPLE_NUM,
                              valid_features=None):
        LOGGER.info("find bin split points")

        if not isinstance(method, str):
            raise TypeError("quantile method should be a str!!!")

        if method == "bin_by_data_block":
            bin_split_points = Quantile.gen_bin_by_merge_data_block(data_instance, bin_num, bin_gap, valid_features)
        elif method == "bin_by_sample_data":
            bin_split_points = Quantile.gen_bin_by_sample_data(data_instance, bin_num,
                                                               bin_gap, bin_sample_num, valid_features)
        else:
            raise NotImplementedError("quantile method %s is not support yes!!" % (method))
        return bin_split_points

    @staticmethod
    def gen_bin_by_merge_data_block(data_instance, bin_num, bin_gap, valid_features):
        LOGGER.info("fgen bin split points by merge data block")

        generate_bin_by_batch_func = functools.partial(Quantile.generate_bin_by_batch,
                                                       [bin_num, bin_gap, valid_features])
        distributed_sample_bins = data_instance.mapPartitions(generate_bin_by_batch_func)

        bin_split_point_list = [bin_split_points for (key, bin_split_points) in list(distributed_sample_bins.collect())]

        if not bin_split_point_list:
            raise ValueError("no sample bins find!!!")

        bin_split_points = Quantile.merge_bin_split_points(bin_split_point_list, bin_num, bin_gap)
        return bin_split_points

    @staticmethod
    def generate_bin_by_batch(param_list, key_value_tuples):
        samples = []
        non_empty_data_block = False

        for key, instance in key_value_tuples:
            samples.append(instance)
            non_empty_data_block = True
        if not non_empty_data_block:
            raise ValueError("data block has no data!!!")

        bin_num, bin_gap, valid_features = param_list
        return Quantile.gen_bin_by_data_block(samples, bin_num, bin_gap, valid_features)

    @staticmethod
    def merge_bin_split_points(bin_split_point_list, bin_num=DEFAULT_BIN_NUM, bin_gap=DEFAULT_BIN_GAP):
        LOGGER.info("fmerge bin split points")

        feature_num = len(bin_split_point_list[0])
        all_bin_split_points = [[] for i in range(feature_num)]
        for bin_split_points in bin_split_point_list:
            for i in range(feature_num):
                all_bin_split_points[i].extend(bin_split_points[i].tolist())

        all_bin_split_points = [sorted(bin_split_points) for bin_split_points in all_bin_split_points]

        for i in range(feature_num):
            split_points = []
            bin_split_points = all_bin_split_points[i]
            split_bin_num = 0

            for j in range(len(bin_split_points)):
                if j == 0 or np.fabs(bin_split_points[j] - bin_split_points[j - 1]) >= bin_gap:
                    split_points.append(bin_split_points[j])
                    split_bin_num += 1

            if split_bin_num > bin_num:
                split_points = [split_points[idx] for idx in
                                range(0, split_bin_num, (split_bin_num + bin_num - 1) // bin_num)]

            all_bin_split_points[i] = np.asarray(split_points)

        return np.asarray(all_bin_split_points)

    @staticmethod
    def gen_bin_by_sample_data(data_instance, bin_num=DEFAULT_BIN_NUM, bin_gap=DEFAULT_BIN_GAP,
                               bin_sample_num=DEFAULT_BIN_NUM, valid_features=None):
        LOGGER.info("gen bin by sample data set")
        sample_datas = Quantile.sample_data(data_instance, bin_sample_num)

        samples = []
        for _, block_data in sample_datas:
            if block_data is not None:
                samples.append(block_data)

        return Quantile.gen_bin_by_data_block(samples, bin_num, bin_gap, valid_features)

    @staticmethod
    def gen_bin_by_data_block(data, bin_num=DEFAULT_BIN_NUM, bin_gap=DEFAULT_BIN_GAP, valid_features=None):
        bin_split_points = []
        if type(data[0].features).__name__ == "ndarray":
            feature_num = data[0].features.shape[0]
        else:
            feature_num = data[0].features.get_shape()

        data_num = len(data)
        sparse_data = False

        for fid in range(feature_num):
            if valid_features is not None and not valid_features[fid]:
                bin_split_points.append(np.asarray([]))
                continue

            if type(data[0].features).__name__ == 'ndarray':
                feature_values = [row.features[fid] for row in data]
            else:
                feature_values = list(filter(lambda _feature: _feature != 0,
                                             [row.features.get_data(fid, 0) for row in data]))
                zeros = data_num - len(feature_values)
                sparse_data = True

            if sparse_data is False:
                distinct_values = np.unique(feature_values)
            else:
                feature_values.append(0)
                distinct_values = np.unique(feature_values)
                feature_values.pop()

            distincts = []
            distinct_count = 1
            distincts.append(distinct_values[0])

            for i in range(1, distinct_values.shape[0]):
                if np.fabs(distinct_values[i] - distincts[-1]) < bin_gap:
                    pass
                else:
                    distinct_count += 1
                    distincts.append(distinct_values[i])

            if distinct_count <= bin_num:
                bin_split_points.append(np.asarray(distincts))
                continue

            if sparse_data and zeros > 0:
                if zeros == data_num:
                    bin_split_points.append(np.asarray([0]))
                    continue

                feature_values = sorted(feature_values)
                negative = 0
                positions = [int(data_num * 1.0 / bin_num * (i + 1)) for i in range(bin_num)]

                percentiles = []
                if feature_values[0] > 0.0:
                    for pos in positions:
                        if pos <= zeros:
                            percentiles.append(0)
                        else:
                            percentiles.append(feature_values[pos - zeros - 1])
                elif feature_values[-1] < 0.0:
                    for pos in positions:
                        if pos < data_num - zeros:
                            percentiles.append(feature_values[pos])
                        else:
                            percentiles.append(0)
                else:
                    for x in feature_values:
                        if x < 0:
                            negative += 1
                        else:
                            break
                    for pos in positions:
                        if pos < negative:
                            percentiles.append(feature_values[pos])
                        elif pos < negative + zeros:
                            percentiles.append(0)
                        else:
                            percentiles.append(feature_values[pos - zeros - negative])
                    percentiles = np.asarray(percentiles)

            else:
                percentile_list = [100.0 / bin_num * (i + 1) for i in range(bin_num)]
                percentiles = np.percentile(feature_values, percentile_list)

            percentiles = np.asarray(percentiles)
            split_points = []
            for i in range(percentiles.shape[0]):
                if i == 0 or np.fabs(percentiles[i] - percentiles[i - 1]) >= bin_gap:
                    split_points.append(percentiles[i])

            bin_split_points.append(np.asarray(split_points))

        return bin_split_points

    @staticmethod
    def sample_data(data_instance, bin_sample_num=DEFAULT_BIN_SAMPLE_NUM):
        LOGGER.info("fsample data set")

        data_key_none_value = data_instance.mapValues(lambda value: None)
        data_key_none_value_tuple = list(data_key_none_value.collect())

        data_num = len(data_key_none_value_tuple)

        if data_num <= bin_sample_num:
            data_keys = [(key, _) for (key, _) in data_key_none_value_tuple]
        else:
            sample_idxs = np.random.choice(data_num, bin_sample_num, replace=False)
            data_keys = [data_key_none_value_tuple[idx] for idx in sample_idxs]

        data_key_table = eggroll.parallelize(data_keys, include_key=True)
        sample_data = list(data_key_table.join(data_instance, lambda x, y: y).collect())
        return sample_data

    @staticmethod
    def convert_instance_to_bin(instance, bin_split_points=None):
        sparse_data = False
        if type(instance.features).__name__ == "ndarray":
            feature_shape = instance.features.shape[0]
        else:
            feature_shape = instance.features.get_shape()
            sparse_data = True
            indices = []

        data_format = type(instance.features).__name__

        features = instance.features

        bins = []

        if sparse_data:
            feature_values = [kv for kv in features.get_all_data()]
        else:
            feature_values = list(zip(range(features.shape[0]), features.tolist()))

        for fid, feature_value in feature_values:
            bin_id = 0

            if sparse_data:
                indices.append(fid)

            if bin_split_points[fid].shape[0] == 0:
                bins.append(bin_id)
                continue

            if bin_split_points[fid].shape[0] <= 20:
                bin_id = bin_split_points[fid].shape[0]
                for idx in range(bin_split_points[fid].shape[0]):
                    if feature_value <= bin_split_points[fid][idx]:
                        bin_id = idx
                        break

                bins.append(bin_id)
            else:
                if feature_value <= bin_split_points[fid][0]:
                    bin_id = 0
                elif feature_value > bin_split_points[fid][bin_split_points[fid].shape[0] - 1]:
                    bin_id = bin_split_points[fid].shape[0]
                else:
                    left = 0
                    right = bin_split_points[fid].shape[0] - 1
                    while left <= right:
                        idx = (left + right) >> 1

                        if feature_value <= bin_split_points[fid][idx]:
                            bin_id = idx
                            right = idx - 1
                        else:
                            left = idx + 1

                bins.append(bin_id)

        if data_format == "ndarray":
            instance.features = np.array(bins, dtype='int')
        else:
            instance.features = SparseVector(indices, bins, feature_shape)

        return instance
