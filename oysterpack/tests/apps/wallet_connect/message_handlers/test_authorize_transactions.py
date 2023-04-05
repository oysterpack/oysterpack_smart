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

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    SigningAddress,
    EncryptionAddress,
)
from oysterpack.algorand.client.model import MicroAlgos, AppId, Address
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.algorand.messaging.secure_message_client import SecureMessageClient
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    SecureMessageWebsocketHandler,
)
from oysterpack.apps.wallet_connect.domain.activity import (
    TxnActivityId,
    AppActivityId,
    AppActivitySpec,
    TxnActivitySpec,
)
from oysterpack.apps.wallet_connect.message_handlers.authorize_transactions import (
    AuthorizeTransactionsHandler,
)
from oysterpack.apps.wallet_connect.messsages.authorize_transactions import (
    AuthorizeTransactionsRequest,
    AuthorizeTransactionsRequestAccepted,
    AuthorizeTransactionsFailure,
    AuthorizeTransactionsErrCode,
    AuthorizeTransactionsSuccess,
)
from oysterpack.apps.wallet_connect.protocols.wallet_connect_service import (
    WalletConnectService,
    AccountSubscription,
    AccountSubscriptionExpired,
    AppNotRegistered,
    AccountNotRegistered,
    AccountNotOptedIntoApp,
    App,
    AppDisabled,
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


app_admin_private_key = AlgoPrivateKey()


@dataclass(slots=True)
class WalletConnectServiceMock(WalletConnectService):
    account_has_subscription: bool = True
    account_subscription_expired: bool = False

    app_keys_registered_: bool = True
    app_registered_: bool = True
    app_enabled_: bool = True
    app_admin_: Address = app_admin_private_key.signing_address

    account_registered_: bool = True
    account_opted_in_app_: bool = True
    app_activity_registered_: bool = True
    app_activity_spec: Callable[[AppActivityId], AppActivitySpec] | None = None
    txn_activity_spec: Callable[[TxnActivityId], TxnActivitySpec] | None = None
    authorize_transactions_: bool = True

    async def app_keys_registered(
        self,
        app_id: AppId,
        signing_address: SigningAddress,
        encryption_address: EncryptionAddress,
    ) -> bool:
        await asyncio.sleep(0)
        return self.app_keys_registered_

    async def lookup_app(self, app_id: AppId) -> App | None:
        await asyncio.sleep(0)
        if not self.app_registered_:
            return None
        return App(
            app_id=app_id,
            name="Foo",
            url="https://app.foo.com",
            enabled=self.app_enabled_,
            admin=self.app_admin_,
        )

    async def account_opted_in_app(self, account: Address, app_id: AppId) -> bool:
        await asyncio.sleep(0)
        return self.account_opted_in_app_

    async def wallet_connected(self, account: Address, app_id: AppId) -> bool:
        await asyncio.sleep(0)
        app = await self.lookup_app(app_id)
        if app is None:
            raise AppNotRegistered()
        if not app.enabled:
            raise AppDisabled()

        subscription = await self.get_account_subscription(account)
        if subscription is None:
            raise AccountNotRegistered()
        if subscription.expired:
            raise AccountSubscriptionExpired()

        if not self.account_opted_in_app_:
            raise AccountNotOptedIntoApp()

        return self.account_registered_

    async def get_account_subscription(
        self,
        account: Address,
    ) -> AccountSubscription | None:
        await asyncio.sleep(0)
        if not self.account_has_subscription:
            return None

        if self.account_subscription_expired:
            return AccountSubscription(
                account=account,
                expiration=datetime.now(UTC) - timedelta(days=1),
                blockchain_timestamp=datetime.now(UTC),
            )
        return AccountSubscription(
            account=account,
            expiration=datetime.now(UTC) + timedelta(days=7),
            blockchain_timestamp=datetime.now(UTC),
        )

    async def app_activity_registered(
        self, app_id: AppId, app_activity_id: AppActivityId
    ) -> bool:
        await asyncio.sleep(0)
        return self.app_activity_registered_

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

    async def authorize_transactions(
        self, request: AuthorizeTransactionsRequest
    ) -> bool:
        await asyncio.sleep(0)
        return self.authorize_transactions_


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
                AuthorizeTransactionsHandler(
                    wallet_connect=WalletConnectServiceMock(),
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
        request = AuthorizeTransactionsRequest(
            app_id=AppId(100),
            authorizer=self.sender_private_key.signing_address,
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
                    for i in range(1, 11):
                        start = time.perf_counter_ns()
                        await client.send(
                            request,
                            self.recipient_private_key.encryption_address,
                        )
                        sent = time.perf_counter_ns()
                        msg = await asyncio.wait_for(client.recv(), 0.1)
                        end = time.perf_counter_ns()
                        logger.info(
                            f"message #{i} sent time: %s",
                            timedelta(
                                microseconds=(sent - start) / 1_000
                            ).total_seconds(),
                        )
                        logger.info(
                            f"message #{i} processing time: %s",
                            timedelta(
                                microseconds=(end - sent) / 1_000
                            ).total_seconds(),
                        )
                        logger.info(
                            f"total message #{i} send/recv time: %s",
                            timedelta(
                                microseconds=(end - start) / 1_000
                            ).total_seconds(),
                        )
                        if msg.msg_type == AuthorizeTransactionsFailure.message_type():
                            failure = AuthorizeTransactionsFailure.unpack(msg.data)
                            self.fail(failure)

                        self.assertEqual(
                            AuthorizeTransactionsRequestAccepted.message_type(),
                            msg.msg_type,
                        )
                        AuthorizeTransactionsRequestAccepted.unpack(msg.data)

                        msg = await asyncio.wait_for(client.recv(), 0.1)
                        self.assertEqual(
                            AuthorizeTransactionsSuccess.message_type(),
                            msg.msg_type,
                        )

    async def test_failure_scenarios(self):
        # SETUP
        txn = transfer_algo(
            sender=self.sender_private_key.signing_address,
            receiver=self.recipient_private_key.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        request = AuthorizeTransactionsRequest(
            app_id=AppId(100),
            authorizer=self.sender_private_key.signing_address,
            transactions=[(txn, TxnActivityId())],
            app_activity_id=AppActivityId(),
        )

        async def run_test(
            name: str,
            multisig_service: WalletConnectService,
            expected_err_code: AuthorizeTransactionsErrCode,
        ):
            secure_message_handler = SecureMessageHandler(
                private_key=self.recipient_private_key,
                message_handlers=[
                    AuthorizeTransactionsHandler(wallet_connect=multisig_service)
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

                                self.assertEqual(
                                    AuthorizeTransactionsFailure.message_type(),
                                    msg.msg_type,
                                )
                                failure = AuthorizeTransactionsFailure.unpack(msg.data)
                                self.assertEqual(expected_err_code, failure.code)

                                await asyncio.sleep(0)

        await run_test(
            name="app is not registered",
            multisig_service=WalletConnectServiceMock(
                app_registered_=False,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AppNotRegistered,
        )
        await run_test(
            name="account not opted into app",
            multisig_service=WalletConnectServiceMock(
                account_opted_in_app_=False,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AccountNotOptedIntoApp,
        )
        await run_test(
            name="signer not subscribed",
            multisig_service=WalletConnectServiceMock(
                account_has_subscription=False,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AccountNotRegistered,
        )
        await run_test(
            name="signer subscription expired",
            multisig_service=WalletConnectServiceMock(
                account_subscription_expired=True,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AccountSubscriptionExpired,
        )
        await run_test(
            name="account has no subscription",
            multisig_service=WalletConnectServiceMock(
                account_has_subscription=False,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AccountNotRegistered,
        )
        await run_test(
            name="app activity not registered",
            multisig_service=WalletConnectServiceMock(
                app_activity_registered_=False,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AppActivityNotRegistered,
        )
        await run_test(
            name="app activity validation failed",
            multisig_service=WalletConnectServiceMock(
                app_activity_spec=lambda app_activity_id: AppActivitySpecMock(
                    activity_id=app_activity_id,
                    name="name",
                    description="description",
                    validation_exception=Exception("app activity validation failed"),
                ),
            ),
            expected_err_code=AuthorizeTransactionsErrCode.InvalidAppActivity,
        )


if __name__ == "__main__":
    unittest.main()
