import asyncio
import time
import unittest
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import timedelta, datetime, UTC
from typing import Callable

from algosdk.account import generate_account
from algosdk.transaction import Transaction
from beaker.consts import algo
from black import Tuple
from websockets.legacy.client import connect

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import MicroAlgos, AppId, Address
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.algorand.messaging.secure_message_client import SecureMessageClient
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    SecureMessageWebsocketHandler,
)
from oysterpack.apps.multisig_wallet_connect.domain.activity import (
    TxnActivityId,
    AppActivityId,
    AppActivitySpec,
    TxnActivitySpec,
)
from oysterpack.apps.multisig_wallet_connect.message_handlers.sign_transactions import (
    SignTransactionsHandler,
)
from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    SignTransactionsRequest,
    SignTransactionsRequestAccepted, SignTransactionsFailure, ErrCode,
)
from oysterpack.apps.multisig_wallet_connect.protocols.multisig_service import (
    MultisigService,
    AccountSubscription,
)
from tests.algorand.messaging import server_ssl_context, client_ssl_context
from tests.algorand.test_support import AlgorandTestCase
from tests.support.websockets import create_websocket_server
from tests.test_support import OysterPackIsolatedAsyncioTestCase


class AppActivitySpecMock(AppActivitySpec):
    def __init__(
            self,
            activity_id: AppActivityId,
            name: str,
            description: str,
            validation_exception: Exception | None = None,
    ):
        super().__init__(
            activity_id=activity_id,
            name=name,
            description=description,
        )
        self._validation_exception = validation_exception

    async def validate(self, txns: list[Tuple[Transaction, TxnActivityId]]):
        if self._validation_exception:
            raise self._validation_exception


class TxnActivitySpecMock(TxnActivitySpec):
    def __init__(
            self,
            activity_id: TxnActivityId,
            name: str,
            description: str,
            validation_exception: Exception | None = None,
    ):
        super().__init__(
            activity_id=activity_id,
            name=name,
            description=description,
        )
        self._validation_exception = validation_exception

    async def validate(self, txn: Transaction):
        if self._validation_exception:
            raise self._validation_exception


@dataclass(slots=True)
class MultisigServiceMock(MultisigService):
    account_has_subscription: bool = True
    account_subscription_expired: bool = False

    app_registered: bool = True
    account_registered: bool = True
    app_activity_registered: bool = True
    app_activity_spec: Callable[[AppActivityId], AppActivitySpec] | None = None
    txn_activity_spec: Callable[[TxnActivityId], TxnActivitySpec] | None = None

    async def is_app_registered(self, app_id: AppId) -> bool:
        return self.app_registered

    async def is_account_registered(self, account: Address, app_id: AppId) -> bool:
        return self.account_registered

    async def get_account_subscription(self, account: Address) -> AccountSubscription | None:
        if not self.account_has_subscription:
            return None

        if self.account_subscription_expired:
            return AccountSubscription(
                account=account,
                expiration=datetime.now(UTC) - timedelta(days=1),
                blockchain_timestamp=datetime.now(UTC)
            )
        return AccountSubscription(
            account=account,
            expiration=datetime.now(UTC) + timedelta(days=7),
            blockchain_timestamp=datetime.now(UTC)
        )

    async def is_app_activity_registered(
            self, app_id: AppId, app_activity_id: AppActivityId
    ) -> bool:
        return self.app_activity_registered

    def get_app_activity_spec(
            self, app_activity_id: AppActivityId
    ) -> AppActivitySpec | None:
        if self.app_activity_spec:
            return self.app_activity_spec(app_activity_id)

        return AppActivitySpecMock(
            activity_id=app_activity_id,
            name="name",
            description="description",
        )

    def get_txn_activity_spec(
            self, txn_activity_id: TxnActivityId
    ) -> TxnActivitySpec | None:
        if self.txn_activity_spec:
            return self.txn_activity_spec(txn_activity_id)

        return TxnActivitySpecMock(
            activity_id=txn_activity_id, name="name", description="description"
        )


class SignTransactionsMessageHandlerTestCase(
    AlgorandTestCase, OysterPackIsolatedAsyncioTestCase
):
    executor: ProcessPoolExecutor

    @classmethod
    def setUpClass(cls) -> None:
        cls.executor = ProcessPoolExecutor()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.executor.shutdown(wait=True)

    def setUp(self) -> None:
        self.sender_private_key = AlgoPrivateKey(generate_account()[0])
        self.recipient_private_key = AlgoPrivateKey(generate_account()[0])

    async def test_single_transaction(self):
        logger = super().get_logger("test_single_transaction")

        # SETUP
        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[
                SignTransactionsHandler(
                    multisig_service=MultisigServiceMock(),
                )
            ],
            executor=self.executor,
        )

        txn = transfer_algo(
            sender=self.sender_private_key.signing_address,
            receiver=self.recipient_private_key.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        request = SignTransactionsRequest(
            app_id=AppId(100),
            signer=self.sender_private_key.signing_address,
            transactions=[(txn, TxnActivityId())],
            app_activity_id=AppActivityId(),
        )

        server = create_websocket_server(
            handler=SecureMessageWebsocketHandler(handler=secure_message_handler),
            ssl_context=server_ssl_context(),
        )

        async with server.start_server() as server:
            async with connect(
                    f"wss://localhost:{server.port}",
                    ssl=client_ssl_context(),
            ) as websocket:
                async with SecureMessageClient(
                        websocket=websocket,
                        private_key=self.sender_private_key,
                        executor=self.executor,
                ).context() as client:
                    for _ in range(10):
                        start = time.perf_counter_ns()
                        await client.send(
                            request,
                            self.recipient_private_key.encryption_address,
                        )
                        sent = time.perf_counter_ns()
                        msg = await asyncio.wait_for(client.recv(), 0.1)
                        end = time.perf_counter_ns()
                        logger.info(
                            "message sent time: %s",
                            timedelta(
                                microseconds=(sent - start) / 1_000
                            ).total_seconds(),
                        )
                        logger.info(
                            "message processing time: %s",
                            timedelta(
                                microseconds=(end - sent) / 1_000
                            ).total_seconds(),
                        )
                        logger.info(
                            "total message send/recv time: %s",
                            timedelta(
                                microseconds=(end - start) / 1_000
                            ).total_seconds(),
                        )

                        if msg.msg_type == SignTransactionsFailure.message_type():
                            failure = SignTransactionsFailure.unpack(msg.data)
                            self.fail(failure)

                        self.assertEqual(
                            SignTransactionsRequestAccepted.message_type(), msg.msg_type
                        )
                        SignTransactionsRequestAccepted.unpack(msg.data)

    async def test_failure_scenarios(self):
        # SETUP
        txn = transfer_algo(
            sender=self.sender_private_key.signing_address,
            receiver=self.recipient_private_key.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        request = SignTransactionsRequest(
            app_id=AppId(100),
            signer=self.sender_private_key.signing_address,
            transactions=[(txn, TxnActivityId())],
            app_activity_id=AppActivityId(),
        )

        async def run_test(
                name: str,
                multisig_service: MultisigService,
                expected_err_code: ErrCode):
            secure_message_handler = SecureMessageHandler(
                private_key=self.recipient_private_key,
                message_handlers=[
                    SignTransactionsHandler(multisig_service=multisig_service)
                ],
                executor=self.executor,
            )
            server = create_websocket_server(
                handler=SecureMessageWebsocketHandler(handler=secure_message_handler),
                ssl_context=server_ssl_context(),
            )

            async with server.start_server() as server:
                async with connect(
                        f"wss://localhost:{server.port}",
                        ssl=client_ssl_context(),
                ) as websocket:
                    async with SecureMessageClient(
                            websocket=websocket,
                            private_key=self.sender_private_key,
                            executor=self.executor,
                    ).context() as client:
                        with self.subTest(name):
                            for _ in range(2):
                                await client.send(
                                    request,
                                    self.recipient_private_key.encryption_address,
                                )
                                msg = await asyncio.wait_for(client.recv(), 0.1)

                                self.assertEqual(SignTransactionsFailure.message_type(), msg.msg_type)
                                failure = SignTransactionsFailure.unpack(msg.data)
                                self.assertEqual(expected_err_code, failure.code)

                                await asyncio.sleep(0)

        await run_test(
            name="signer not subscribed",
            multisig_service=MultisigServiceMock(
                account_has_subscription=False,
            ),
            expected_err_code=ErrCode.SignerNotSubscribed,
        )

        await run_test(
            name="signer subscription expired",
            multisig_service=MultisigServiceMock(
                account_subscription_expired=True,
            ),
            expected_err_code=ErrCode.SignerSubscriptionExpired,
        )
        await run_test(
            name="account has no subscription",
            multisig_service=MultisigServiceMock(
                account_has_subscription=False,
            ),
            expected_err_code=ErrCode.SignerNotSubscribed,
        )
        await run_test(
            name="app activity not registered",
            multisig_service=MultisigServiceMock(
                app_activity_registered=False,
            ),
            expected_err_code=ErrCode.AppActivityNotRegistered,
        )
        await run_test(
            name="app activity validation failed",
            multisig_service=MultisigServiceMock(
                app_activity_spec=lambda app_activity_id: AppActivitySpecMock(
                    activity_id=app_activity_id,
                    name="name",
                    description="description",
                    validation_exception=Exception("app activity validation failed")
                ),
            ),
            expected_err_code=ErrCode.InvalidAppActivity,
        )


if __name__ == "__main__":
    unittest.main()
