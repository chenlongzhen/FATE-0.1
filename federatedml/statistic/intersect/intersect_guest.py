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

import gmpy2
import hashlib
import random
from arch.api.federation import remote, get
from arch.api.utils import log_utils
from federatedml.secureprotol import gmpy_math
from federatedml.statistic.intersect import Intersect
from federatedml.util import consts
from federatedml.util.transfer_variable import RawIntersectTransferVariable
from federatedml.util.transfer_variable import RsaIntersectTransferVariable

LOGGER = log_utils.getLogger()


class RsaIntersectionGuest(Intersect):
    def __init__(self, intersect_params):
        self.send_intersect_id_flag = intersect_params.is_send_intersect_ids
        self.random_bit = intersect_params.random_bit

        self.e = None
        self.n = None
        self.transfer_variable = RsaIntersectTransferVariable()

    @staticmethod
    def hash(value):
        return hashlib.sha256(bytes(str(value), encoding='utf-8')).hexdigest()

    def run(self, data_instances):
        LOGGER.info("Start ras intersection")
        public_key = get(name=self.transfer_variable.rsa_pubkey.name,
                         tag=self.transfer_variable.generate_transferid(self.transfer_variable.rsa_pubkey),
                         idx=0)

        LOGGER.info("Get RAS public_key:{} from Host".format(public_key))
        self.e = public_key["e"]
        self.n = public_key["n"]

        # generate random value and sent intersect guest ids to guest
        # table(sid, r)
        table_random_value = data_instances.mapValues(
            lambda v: random.SystemRandom().getrandbits(self.random_bit))

        # table(sid, hash(sid))
        table_hash_sid = data_instances.map(lambda k, v:
                                            (k, int(RsaIntersectionGuest.hash(k),
                                                    16)))
        # table(sid. r^e % n *hash(sid))
        table_guest_id = table_random_value.join(table_hash_sid, lambda r, h: h * gmpy_math.powmod(r, self.e,
                                                                                                   self.n))
        # table(r^e % n *hash(sid), 1)
        table_send_guest_id = table_guest_id.map(lambda k, v: (v, 1))
        remote(table_send_guest_id,
               name=self.transfer_variable.intersect_guest_ids.name,
               tag=self.transfer_variable.generate_transferid(self.transfer_variable.intersect_guest_ids),
               role=consts.HOST,
               idx=0)
        LOGGER.info("Remote guest_id to Host")

        # table(r^e % n *hash(sid), sid)
        table_exchange_guest_id = table_guest_id.map(lambda k, v: (v, k))

        # Recv host_ids_process
        # table(host_id_process, 1)
        table_host_ids_process = get(name=self.transfer_variable.intersect_host_ids_process.name,
                                     tag=self.transfer_variable.generate_transferid(
                                         self.transfer_variable.intersect_host_ids_process),
                                     idx=0)
        LOGGER.info("Get host_ids_process from Host")

        # Recv process guest ids
        # table(r^e % n *hash(sid), guest_id_process)
        table_recv_guest_ids_process = get(name=self.transfer_variable.intersect_guest_ids_process.name,
                                           tag=self.transfer_variable.generate_transferid(
                                               self.transfer_variable.intersect_guest_ids_process),
                                           # role=consts.HOST,
                                           idx=0)
        LOGGER.info("Get guest_ids_process from Host")

        # table(r^e % n *hash(sid), sid, guest_ids_process)
        table_join_guest_ids_process = table_exchange_guest_id.join(table_recv_guest_ids_process,
                                                                    lambda sid, g: (sid,
                                                                                    g))
        # table(sid, guest_ids_process)
        table_sid_guest_ids_process = table_join_guest_ids_process.map(
            lambda k, v: (v[0], v[1]))

        # table(sid, hash(guest_ids_process/r)))
        table_sid_guest_ids_process_final = table_sid_guest_ids_process.join(table_random_value,
                                                                             lambda g, r: hashlib.sha256(bytes(
                                                                                 str(
                                                                                     gmpy2.divm(int(g), int(r), self.n)
                                                                                 ), encoding="utf-8")).hexdigest()
                                                                             )

        # table(hash(guest_ids_process/r), sid)
        table_guest_ids_process_final_sid = table_sid_guest_ids_process_final.map(
            lambda k, v: (v, k))

        table_intersect_ids = table_guest_ids_process_final_sid.join(table_host_ids_process, lambda sid, h: sid)
        LOGGER.info("Finish intersect_ids computing")

        # send intersect id
        if self.send_intersect_id_flag:
            remote(table_intersect_ids,
                   name=self.transfer_variable.intersect_ids.name,
                   tag=self.transfer_variable.generate_transferid(self.transfer_variable.intersect_ids),
                   role=consts.HOST,
                   idx=0)
            LOGGER.info("Remote intersect ids to Host!")
        else:
            LOGGER.info("Not send intersect ids to Host!")
        return table_intersect_ids


class RawIntersectionGuest(Intersect):
    def __init__(self, intersect_params):
        self.send_intersect_id_flag = intersect_params.is_send_intersect_ids
        self.transfer_variable = RawIntersectTransferVariable()

    def run(self, data_instances):
        LOGGER.info("Start raw intersection")
        intersect_host_ids = get(name=self.transfer_variable.intersect_host_ids.name,
                                 tag=self.transfer_variable.generate_transferid(
                                     self.transfer_variable.intersect_host_ids),
                                 idx=0)

        LOGGER.info("Get intersect_host_ids from Host")
        intersect_ids = intersect_host_ids.join(data_instances, lambda i, d: 1)
        LOGGER.info("Finish intersect_ids computing")

        if self.send_intersect_id_flag:
            remote(intersect_ids,
                   name=self.transfer_variable.intersect_ids.name,
                   tag=self.transfer_variable.generate_transferid(self.transfer_variable.intersect_ids),
                   role=consts.HOST,
                   idx=0)
            LOGGER.info("Remote intersect ids to Host")
        return intersect_ids
