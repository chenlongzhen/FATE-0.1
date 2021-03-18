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

from federatedml.ftl.encryption.encryption import encrypt_matrix, decrypt_matrix
import numpy as np


def distribute_compute_XY(X, Y):
    """
    compute X * Y
    :param X: DTable, with shape (feature_dim, sample_dim)
    :param Y: DTable, with shape (feature_dim, sample_dim)
    :return: a DTable
    """
    R = X.join(Y, lambda x, y: x * y)
    val = R.collect()
    table = dict(val)
    return table


def distribute_compute_X_plus_Y(X, Y):
    """
    compute X + Y
    :param X: DTable, with shape (feature_dim, sample_dim)
    :param Y: DTable, with shape (feature_dim, sample_dim)
    :return: a DTable
    """

    R = X.join(Y, lambda x, y: x + y)
    val = R.collect()
    table = dict(val)
    return table


def distribute_compute_hSum_XY(X, Y):
    """
    compute np.sum(X * Y, axis=1)
    :param X: DTable, with shape (feature_dim, sample_dim)
    :param Y: DTable, with shape (feature_dim, sample_dim)
    :return: a DTable
    """
    R = X.join(Y, lambda x, y: np.sum(x * y))
    val = R.collect()
    table = dict(val)
    return table


def distribute_compute_vAvg_XY(X, Y, sample_dim):
    """
    compute np.mean(X * Y, axis=0)
    :param X: DTable, with shape (feature_dim, sample_dim)
    :param Y: DTable, with shape (feature_dim, sample_dim) or (1, sample_dim)
    :param feature_dim:
    :param sample_dim:
    :return: a DTable
    """

    R = X.join(Y, lambda x, y: y * x / sample_dim)
    result = R.reduce(lambda agg_val, v: agg_val + v)
    return result


def distribute_encrypt(public_key, X):
    """
    encrypt X
    :param X: DTable
    :return: a dictionary
    """

    X2 = X.mapValues(lambda x: encrypt_matrix(public_key, x))
    val = X2.collect()
    val = dict(val)
    return val


def distribute_decrypt(private_key, X):
    """
    decrypt X
    :param X: DTable
    :return: a dictionary
    """

    X2 = X.mapValues(lambda x: decrypt_matrix(private_key, x))
    val = X2.collect()
    val = dict(val)
    return val
