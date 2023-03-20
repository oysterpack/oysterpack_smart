import unittest

from beaker.consts import algo
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import AppId, MicroAlgos, TxnId
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    SignTransactionsRequest,
    RequestId,
    SignTransactionsResult,
)
from tests.algorand.test_support import AlgorandTestCase


class SignTransactionsTestCase(AlgorandTestCase):
    def test_request_pack_unpack(self):
        sender = AlgoPrivateKey()
        receiver = AlgoPrivateKey()

        txn = transfer_algo(
            sender=sender.signing_address,
            receiver=receiver.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )

        request = SignTransactionsRequest(
            request_id=RequestId(),
            app_id=AppId(100),
            signer=sender.signing_address,
            transactions=[txn],
            description="ALGO transfer",
        )
        packed_request = request.pack()
        print(f"len(packed_request) = {len(packed_request)}")
        request_2 = SignTransactionsRequest.unpack(packed_request)
        self.assertEqual(request, request_2)

    def test_result_pack_unpack(self):
        result = SignTransactionsResult(
            request_id=RequestId(), transaction_ids=[TxnId(str(ULID()))]
        )
        packed_result = result.pack()
        print(f"len(packed_request) = {len(packed_result)}")
        result_2 = SignTransactionsResult.unpack(packed_result)
        self.assertEqual(result, result_2)


if __name__ == "__main__":
    unittest.main()
