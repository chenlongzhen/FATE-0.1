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

import csv
import numpy as np
import time
from sklearn.preprocessing.data import StandardScaler, OneHotEncoder
import matplotlib.pyplot as plt
from federatedml.feature.instance import Instance
from arch.api.eggroll import parallelize, table


def series_plot(losses, fscores, aucs):

    fig = plt.figure(figsize=(20, 40))

    plt.subplot(311)
    plt.plot(losses)
    plt.xlabel('epoch')
    plt.ylabel('values')
    plt.title("loss")
    plt.grid(True)

    plt.subplot(312)
    plt.plot(fscores)
    plt.xlabel('epoch')
    plt.ylabel('values')
    plt.title("fscore")
    plt.grid(True)

    plt.subplot(313)
    plt.plot(aucs)
    plt.xlabel('epoch')
    plt.ylabel('values')
    plt.title("auc")
    plt.grid(True)

    plt.show()


def balance_X_y(X, y, seed=5):
    np.random.seed(seed)
    num_pos = np.sum(y == 1)
    num_neg = np.sum(y == -1)
    pos_indexes = [i for (i, _y) in enumerate(y) if _y > 0]
    neg_indexes = [i for (i, _y) in enumerate(y) if _y < 0]

    if num_pos < num_neg:
        np.random.shuffle(neg_indexes)
        rand_indexes = neg_indexes[:num_pos]
        indexes = pos_indexes + rand_indexes
        y = [y[i] for i in indexes]
        X = [X[i] for i in indexes]
    return np.array(X), np.array(y)


def shuffle_X_y(X, y, seed=5):
    np.random.seed(seed)
    data_size = X.shape[0]
    shuffle_index = list(range(data_size))
    np.random.shuffle(shuffle_index)
    X = X[shuffle_index, :]
    y = y[shuffle_index]
    return X, y


def load_UCI_Credit_Card_data(infile=None, balanced=True, seed=5):

    X = []
    y = []
    sids = []

    with open(infile, "r") as fi:
        fi.readline()
        reader = csv.reader(fi)
        for row in reader:
            sids.append(row[0])
            X.append(row[1:-1])
            y0 = int(row[-1])
            if y0 == 0:
                y0 = -1
            y.append(y0)
    y = np.array(y)

    if balanced:
        X, y = balance_X_y(X, y, seed)

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.float32)

    encoder = OneHotEncoder(categorical_features=[1, 2, 3])
    encoder.fit(X)
    X = encoder.transform(X).toarray()

    X, y = shuffle_X_y(X, y, seed)

    scale_model = StandardScaler()
    X = scale_model.fit_transform(X)

    return X, np.expand_dims(y, axis=1)


def split_data_combined(X, y, overlap_ratio=0.3, ab_split_ratio=0.1, n_feature_b=16):
    data_size = X.shape[0]
    overlap_size = int(data_size * overlap_ratio)
    overlap_indexes = np.array(range(overlap_size))
    A_size = int((data_size - overlap_size) * (1 - ab_split_ratio))
    X_A = X[:A_size + overlap_size, n_feature_b:]
    y_A = y[:A_size + overlap_size, :]
    X_B = np.vstack((X[:overlap_size, :n_feature_b], X[A_size + overlap_size:, :n_feature_b]))
    y_B = np.vstack((y[:overlap_size, :], y[A_size + overlap_size:, :]))
    return X_A, y_A, X_B, y_B, overlap_indexes


def stack_overlap_nonoverlap(data_dict, overlap_data_indexes, nonoverlap_data_indexes):
    data_overlap = []
    for index in overlap_data_indexes:
        data_overlap.append(data_dict[index])
    data_non_overlap = []
    for index in nonoverlap_data_indexes:
        data_non_overlap.append(data_dict[index])
    data_overlap = np.array(data_overlap)
    data_non_overlap = np.array(data_non_overlap)
    if len(data_overlap.shape) == 1:
        data_overlap = np.expand_dims(data_overlap, axis=1)
    if len(data_non_overlap.shape) == 1:
        data_non_overlap = np.expand_dims(data_non_overlap, axis=1)

    # TODO data_non_overlap [] (0, 1)
    data_stack = np.vstack((data_overlap, data_non_overlap))
    return data_stack


def overlapping_samples_converter(target_features_dict, target_sample_indexes, ref_sample_indexes, target_labels_dict=None):

    overlap_indexes = np.intersect1d(target_sample_indexes, ref_sample_indexes, assume_unique=True)
    non_overlap_indexes = np.setdiff1d(target_sample_indexes, overlap_indexes)

    new_overlap_indexes = np.array(range(len(overlap_indexes)))
    new_non_overlap_indexes = np.array(range(len(overlap_indexes), len(overlap_indexes) + len(non_overlap_indexes)))

    features_stack = stack_overlap_nonoverlap(target_features_dict, overlap_indexes, non_overlap_indexes)
    features = np.squeeze(features_stack)

    if target_labels_dict is None:
        return features, new_overlap_indexes, new_non_overlap_indexes,
    else:
        labels_stack = stack_overlap_nonoverlap(target_labels_dict, overlap_indexes, non_overlap_indexes)
        return features, new_overlap_indexes, new_non_overlap_indexes, labels_stack


def split_guest_host_data(X, y, overlap_ratio=0.2, guest_split_ratio=0.5, guest_feature_num=16,
                          tables_name=None, partition=1):
    data_size = X.shape[0]
    overlap_size = int(data_size * overlap_ratio)
    overlap_indexes = np.array(range(overlap_size))
    guest_size = int((data_size - overlap_size) * guest_split_ratio)

    guest_table_ns = "guest_table_ns"
    guest_table_name = "guest_table_name"
    host_table_ns = "host_table_ns"
    host_table_name = "host_table_name"
    if tables_name is not None:
        guest_table_ns = tables_name["guest_table_ns"]
        guest_table_name = tables_name["guest_table_name"]
        host_table_ns = tables_name["host_table_ns"]
        host_table_name = tables_name["host_table_name"]

    guest_temp = []
    for i in range(0, overlap_size + guest_size):
        guest_temp.append((i, Instance(inst_id=None, weight=1.0, features=X[i, :guest_feature_num].reshape(1, -1), label=y[i, 0])))
    guest_data = table(name=guest_table_name, namespace=guest_table_ns, partition=partition)
    guest_data.put_all(guest_temp)

    host_temp = []
    for i in range(0, overlap_size):
        host_temp.append((i, Instance(inst_id=None, weight=1.0, features=X[i, guest_feature_num:].reshape(1, -1), label=y[i, 0])))
    for i in range(overlap_size + guest_size, len(X)):
        host_temp.append((i, Instance(inst_id=None, weight=1.0, features=X[i, guest_feature_num:].reshape(1, -1), label=y[i, 0])))
    host_data = table(name=host_table_name, namespace=host_table_ns, partition=partition)
    host_data.put_all(host_temp)
    return guest_data, host_data, overlap_indexes


def create_data_generator(X, y, start_end_index_list, feature_index_range):
    for (start_index, end_index) in start_end_index_list:
        for i in range(start_index, end_index):
            yield (i, Instance(inst_id=None, weight=1.0,
                               features=X[i, feature_index_range[0]:feature_index_range[1]].reshape(1, -1),
                               label=y[i, 0]))


def create_guest_host_data_generator(X, y, overlap_ratio=0.2, guest_split_ratio=0.5, guest_feature_num=1):
    data_size = X.shape[0]
    overlap_size = int(data_size * overlap_ratio)
    overlap_indexes = np.array(range(overlap_size))
    guest_size = int((data_size - overlap_size) * guest_split_ratio)

    guest_data_generator = create_data_generator(X, y, [(0, overlap_size + guest_size)], (0, guest_feature_num))
    host_data_generator = create_data_generator(X, y, [(0, overlap_size), (overlap_size + guest_size, len(X))], (guest_feature_num, X.shape[-1]))

    return guest_data_generator, host_data_generator, overlap_indexes


def load_guest_host_generators_for_UCI_Credit_Card(file_path, num_samples=None, overlap_ratio=0.2,
                                                   guest_split_ratio=0.5, guest_feature_num=16, balanced=True):

    X, y = load_UCI_Credit_Card_data(infile=file_path, balanced=balanced)

    if num_samples is not None:
        X = X[:num_samples]
        y = y[:num_samples]

    guest_data_generator, host_data_generator, overlap_indexes = create_guest_host_data_generator(X, y,
                                                                                    overlap_ratio=overlap_ratio,
                                                                                    guest_split_ratio=guest_split_ratio,
                                                                                    guest_feature_num=guest_feature_num)

    return guest_data_generator, host_data_generator, overlap_indexes


def load_guest_host_dtable_from_UCI_Credit_Card(file_path, tables_name, num_samples=None, overlap_ratio=0.2,
                                                guest_split_ratio=0.5, guest_feature_num=16, balanced=True):

    X, y = load_UCI_Credit_Card_data(infile=file_path, balanced=balanced)

    if num_samples is not None:
        X = X[:num_samples]
        y = y[:num_samples]

    guest_data, host_data, _ = split_guest_host_data(X, y, overlap_ratio=overlap_ratio,
                                                     guest_split_ratio=guest_split_ratio,
                                                     guest_feature_num=guest_feature_num,
                                                     tables_name=tables_name)

    return guest_data, host_data


def load_model_parameters(model_table_name, model_namespace):
    model = table(model_table_name, model_namespace)
    model_parameters = {}
    for meta_name, meta_value in model.collect():
        model_parameters[meta_name] = meta_value
    return model_parameters


def save_model_parameters(model_parameters, model_table_name, model_namespace):
    dtable = parallelize(model_parameters.items(), include_key=True,
                         name=model_table_name,
                         namespace=model_namespace,
                         error_if_exist=True,
                         persistent=True)
    return dtable


def create_table(data, indexes=None, model_table_name=None, model_namespace=None, persistent=False):
    if indexes is None:
        dtable = parallelize(data, include_key=False,
                             name=model_table_name,
                             namespace=model_namespace,
                             error_if_exist=True,
                             persistent=persistent)
    else:
        data_dict = {}
        for i, index in enumerate(indexes):
            data_dict[index] = data[i]
        dtable = parallelize(data_dict.items(), include_key=True,
                             name=model_table_name,
                             namespace=model_namespace,
                             error_if_exist=True,
                             persistent=persistent)
    return dtable


def save_data_to_eggroll_table(data, namespace, table_name, partition=1):
    data_table = table(table_name, namespace, partition=partition, create_if_missing=True, error_if_exist=True)
    data_table.put_all(data)
    return data_table


def convert_dict_to_array(data_dict):
    data_list = []
    for _, v in data_dict.items():
        data_list.append(v)
    return np.array(data_list)


def convert_instance_table_to_dict(instances_table):
    features_dict = {}
    labels_dict = {}
    instances_indexes = []
    for k, v in instances_table.collect():
        instances_indexes.append(k)
        features_dict[k] = v.features
        labels_dict[k] = v.label
    return features_dict, labels_dict, instances_indexes


def convert_instance_table_to_array(instances_table):
    features = []
    labels = []
    instances_indexes = []
    for k, v in instances_table.collect():
        instances_indexes.append(k)
        features.append(v.features)
        labels.append(v.label)
    return np.array(features), np.array(labels), instances_indexes


def generate_table_namespace_n_name(input_file_path):
    last = input_file_path.split("/")[-1]
    namespace = last.split(".")[0]
    local_time = time.localtime(time.time())
    table_name = time.strftime("%Y%m%d%H%M%S", local_time)
    return namespace, table_name
