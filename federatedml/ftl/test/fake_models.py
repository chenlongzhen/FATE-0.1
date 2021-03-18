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
from federatedml.optim.convergence import ConvergeFunction


class FakeAutoencoder(object):

    def __init__(self, an_id):
        super(FakeAutoencoder, self).__init__()
        self.id = str(an_id)

    def build(self, encode_dim, Wh=None, bh=None):
        self.encode_dim = encode_dim
        self.Wh = Wh
        self.bh = bh

    def transform(self, X):
        return X

    def compute_gradients(self, X):
        N = len(X)
        Whs = []
        bhs = []
        for i in range(N):
            Whs.append(self.Wh.copy())
            bhs.append(self.bh.copy())
        return [np.array(Whs), np.array(bhs)]

    def apply_gradients(self, gradients):
        pass

    def backpropogate(self, X, y, in_grad):
        # print("in backpropogate with model ", self.id)
        # print("X shape", X.shape)
        # if y is None:
        #     print("y is None")
        # else:
        #     print("y shape", y.shape)
        # print("in_grad shape", in_grad.shape)
        # print("in_grad", in_grad)
        pass

    def predict(self, X):
        return 0.0

    def get_encode_dim(self):
        return self.encode_dim


class FakeFTLModelParam(object):
    def __init__(self, max_iteration=10, batch_size=64, eps=1e-5,
                 alpha=100, lr_decay=0.001, l2_para=1, is_encrypt=True):
        self.max_iter = max_iteration
        self.batch_size = batch_size
        self.eps = eps
        self.alpha = alpha
        self.lr_decay = lr_decay
        self.l2_para = l2_para
        self.is_encrypt = is_encrypt


class FakeDiffConverge(ConvergeFunction):

    def __init__(self, expected_loss, eps=0.00001):
        super(FakeDiffConverge, self).__init__(eps)
        self.eps = eps
        self.expected_loss = expected_loss

    def is_converge(self, loss):
        return True


