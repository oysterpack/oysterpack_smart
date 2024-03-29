import unittest

import msgpack  # type: ignore
from algosdk import transaction
from beaker.consts import algo
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import AppId, MicroAlgos, TxnId
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.apps.wallet_connect.domain.activity import (
    AppActivityId,
)
from oysterpack.apps.wallet_connect.messsages.authorize_transactions import (
    AuthorizeTransactionsRequest,
    AuthorizeTransactionsSuccess,
    AuthorizeTransactionsError,
    AuthorizeTransactionsErrCode,
    AuthorizeTransactionsFailure,
)
from tests.algorand.test_support import AlgorandTestCase


class AuthorizeTransactionsTestCase(AlgorandTestCase):
    def test_request_pack_unpack(self):
        logger = self.get_logger("test_request_pack_unpack")
        sender = AlgoPrivateKey()
        receiver = AlgoPrivateKey()

        with self.subTest("single transaction"):
            txn1 = transfer_algo(
                sender=sender.signing_address,
                receiver=receiver.signing_address,
                amount=MicroAlgos(1 * algo),
                suggested_params=self.algod_client.suggested_params(),
            )

            request = AuthorizeTransactionsRequest(
                app_id=AppId(100),
                authorizer=sender.signing_address,
                transactions=[txn1],
                app_activity_id=AppActivityId(AppId(10)),
            )
            packed = request.pack()
            logger.info(f"message length = {len(packed)}")
            request_2 = AuthorizeTransactionsRequest.unpack(packed)
            self.assertEqual(request, request_2)

        with self.subTest("multiple transactions"):
            txn2 = transfer_algo(
                sender=sender.signing_address,
                receiver=receiver.signing_address,
                amount=MicroAlgos(1 * algo),
                suggested_params=self.algod_client.suggested_params(),
            )
            with self.subTest("txns are not assigned group ids"):
                with self.assertRaises(AuthorizeTransactionsError) as err:
                    AuthorizeTransactionsRequest(
                        app_id=AppId(100),
                        authorizer=sender.signing_address,
                        transactions=[txn1, txn2],
                        app_activity_id=AppActivityId(AppId(10)),
                    )
                self.assertEqual(
                    AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
                )

            with self.subTest("there is more than 1 group ID"):
                txn3 = transfer_algo(
                    sender=sender.signing_address,
                    receiver=receiver.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=self.algod_client.suggested_params(),
                )
                txn4 = transfer_algo(
                    sender=sender.signing_address,
                    receiver=receiver.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=self.algod_client.suggested_params(),
                )
                transaction.assign_group_id([txn1, txn2])
                transaction.assign_group_id([txn3, txn4])
                with self.assertRaises(AuthorizeTransactionsError) as err:
                    AuthorizeTransactionsRequest(
                        app_id=AppId(100),
                        authorizer=sender.signing_address,
                        transactions=[
                            txn1,
                            txn2,
                            txn3,
                            txn4,
                        ],
                        app_activity_id=AppActivityId(AppId(10)),
                    )
                self.assertEqual(
                    AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
                )

            with self.subTest("there is more than 1 group ID"):
                txn3 = transfer_algo(
                    sender=sender.signing_address,
                    receiver=receiver.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=self.algod_client.suggested_params(),
                )
                txn4 = transfer_algo(
                    sender=sender.signing_address,
                    receiver=receiver.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=self.algod_client.suggested_params(),
                )
                transaction.assign_group_id([txn1, txn2])
                transaction.assign_group_id([txn3, txn4])
                with self.assertRaises(AuthorizeTransactionsError) as err:
                    AuthorizeTransactionsRequest(
                        app_id=AppId(100),
                        authorizer=sender.signing_address,
                        transactions=[
                            txn1,
                            txn2,
                            txn3,
                            txn4,
                        ],
                        app_activity_id=AppActivityId(AppId(10)),
                    )
                self.assertEqual(
                    AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
                )

        with self.subTest("multiple transactions"):
            txns = [
                transfer_algo(
                    sender=sender.signing_address,
                    receiver=receiver.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=self.algod_client.suggested_params(),
                )
                for _ in range(3)
            ]
            transaction.assign_group_id(txns)
            AuthorizeTransactionsRequest(
                app_id=AppId(100),
                authorizer=sender.signing_address,
                transactions=txns,
                app_activity_id=AppActivityId(AppId(10)),
            )

    def test_post_create_validations(self):
        sender = AlgoPrivateKey()
        receiver = AlgoPrivateKey()

        txn = transfer_algo(
            sender=sender.signing_address,
            receiver=receiver.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )

        request = AuthorizeTransactionsRequest(
            app_id=AppId(100),
            authorizer=sender.signing_address,
            transactions=[txn],
            app_activity_id=AppActivityId(AppId(10)),
        )
        (
            app_id,
            authorizer,
            txns,
            app_activity_id,
        ) = msgpack.unpackb(request.pack())
        with self.assertRaises(AuthorizeTransactionsError) as err:
            AuthorizeTransactionsRequest.unpack(
                msgpack.packb(
                    (
                        None,
                        authorizer,
                        txns,
                        app_activity_id,
                    )
                )
            )
        self.assertEqual(
            AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
        )
        with self.assertRaises(AuthorizeTransactionsError) as err:
            AuthorizeTransactionsRequest.unpack(
                msgpack.packb(
                    (
                        app_id,
                        None,
                        txns,
                        app_activity_id,
                    )
                )
            )
        self.assertEqual(
            AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
        )
        with self.assertRaises(AuthorizeTransactionsError) as err:
            AuthorizeTransactionsRequest.unpack(
                msgpack.packb(
                    (
                        app_id,
                        authorizer,
                        [],
                        app_activity_id,
                    )
                )
            )
        self.assertEqual(
            AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
        )
        with self.assertRaises(AuthorizeTransactionsError) as err:
            AuthorizeTransactionsRequest.unpack(
                msgpack.packb(
                    (
                        app_id,
                        authorizer,
                        txns,
                        None,
                    )
                )
            )
        self.assertEqual(
            AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
        )
        with self.assertRaises(AuthorizeTransactionsError) as err:
            AuthorizeTransactionsRequest.unpack(
                msgpack.packb(
                    (
                        app_id,
                        "invalid_address",
                        txns,
                        app_activity_id,
                    )
                )
            )
        self.assertEqual(
            AuthorizeTransactionsErrCode.InvalidMessage, err.exception.code
        )

    def test_result_pack_unpack(self):
        logger = self.get_logger("test_result_pack_unpack")
        result = AuthorizeTransactionsSuccess([TxnId(str(ULID()))])
        packed = result.pack()
        logger.info(f"message length = {len(packed)}")
        result_2 = AuthorizeTransactionsSuccess.unpack(packed)
        self.assertEqual(result, result_2)

    def test_error_pack_unpack(self):
        logger = self.get_logger("test_error_pack_unpack")
        err = AuthorizeTransactionsFailure(
            code=AuthorizeTransactionsErrCode.AppNotRegistered,
            message="app is not registered",
        )

        packed = err.pack()
        logger.info(f"message length = {len(packed)}")
        err_2 = AuthorizeTransactionsFailure.unpack(packed)
        self.assertEqual(err, err_2)


if __name__ == "__main__":
    unittest.main()
