import unittest

from algosdk.transaction import Multisig, MultisigTransaction
from beaker.consts import algo
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import AppId, MicroAlgos, TxnId
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.algorand.client.transactions.smart_contract import base64_encode
from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    SignTransactionsRequest,
    RequestId,
    SignTransactionsResult, SignTransactionsError, ErrCode, SignMultisigTransactionsMessage,
)
from tests.algorand.test_support import AlgorandTestCase


class SignTransactionsTestCase(AlgorandTestCase):

    def test_request_pack_unpack(self):
        logger = self.get_logger("test_request_pack_unpack")
        sender = AlgoPrivateKey()
        receiver = AlgoPrivateKey()

        txn = transfer_algo(
            sender=sender.signing_address,
            receiver=receiver.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )

        service_fee = transfer_algo(
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
            service_fee=service_fee,
            description="ALGO transfer",
        )
        packed = request.pack()
        logger.info(f"message length = {len(packed)}")
        request_2 = SignTransactionsRequest.unpack(packed)
        self.assertEqual(request, request_2)

    def test_result_pack_unpack(self):
        logger = self.get_logger("test_result_pack_unpack")
        result = SignTransactionsResult(
            request_id=RequestId(),
            transaction_ids=[TxnId(str(ULID()))],
            service_fee_txid=TxnId(str(ULID())),
        )
        packed = result.pack()
        logger.info(f"message length = {len(packed)}")
        result_2 = SignTransactionsResult.unpack(packed)
        self.assertEqual(result, result_2)

    def test_error_pack_unpack(self):
        logger = self.get_logger("test_error_pack_unpack")
        err = SignTransactionsError(
            request_id=RequestId(),
            code=ErrCode.AppNotRegistered,
            message="app is not registered"
        )

        packed = err.pack()
        logger.info(f"message length = {len(packed)}")
        err_2 = SignTransactionsError.unpack(packed)
        self.assertEqual(err, err_2)

    def test_multisig_msg_pack_unpack(self):
        logger = self.get_logger("test_request_pack_unpack")
        sender = AlgoPrivateKey()
        receiver = AlgoPrivateKey()

        txn = transfer_algo(
            sender=sender.signing_address,
            receiver=receiver.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )

        primary_signer = AlgoPrivateKey()
        secondary_signer = AlgoPrivateKey()

        multisig = Multisig(
            version=1,
            threshold=2,
            addresses=[
                primary_signer.signing_address,
                secondary_signer.signing_address,
            ]
        )

        multisig_txn = MultisigTransaction(
            transaction=txn,
            multisig=multisig
        )

        service_fee = transfer_algo(
            sender=sender.signing_address,
            receiver=receiver.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )

        request = SignMultisigTransactionsMessage(
            request_id=RequestId(),
            app_id=AppId(100),
            signer=sender.signing_address,
            multisig_signer=primary_signer.signing_address,
            transactions=[multisig_txn],
            service_fee=service_fee,
            description="ALGO transfer",
        )
        packed = request.pack()
        logger.info(f"message length = {len(packed)}")
        request_2 = SignMultisigTransactionsMessage.unpack(packed)
        self.assertEqual(request, request_2)

        with self.subTest("with 1 signature"):
            multisig_txn.sign(
                base64_encode(primary_signer.signing_key._signing_key).decode()
            )

            request = SignMultisigTransactionsMessage(
                request_id=RequestId(),
                app_id=AppId(100),
                signer=sender.signing_address,
                multisig_signer=primary_signer.signing_address,
                transactions=[multisig_txn],
                service_fee=service_fee,
                description="ALGO transfer",
            )
            self.assertFalse(request.verify_signatures())
            packed = request.pack()
            logger.info(f"message length = {len(packed)}")
            request_2 = SignMultisigTransactionsMessage.unpack(packed)
            self.assertEqual(request, request_2)

        with self.subTest("with 2 signature2"):
            multisig_txn.sign(
                base64_encode(secondary_signer.signing_key._signing_key).decode()
            )

            request = SignMultisigTransactionsMessage(
                request_id=RequestId(),
                app_id=AppId(100),
                signer=sender.signing_address,
                multisig_signer=primary_signer.signing_address,
                transactions=[multisig_txn],
                service_fee=service_fee,
                description="ALGO transfer",
            )
            self.assertTrue(request.verify_signatures())

            packed = request.pack()
            logger.info(f"message length = {len(packed)}")
            request_2 = SignMultisigTransactionsMessage.unpack(packed)
            self.assertEqual(request, request_2)



if __name__ == "__main__":
    unittest.main()
