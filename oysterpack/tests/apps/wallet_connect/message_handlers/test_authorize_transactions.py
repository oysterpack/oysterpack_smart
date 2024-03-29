import asyncio
import time
import unittest
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import timedelta, datetime, UTC
from typing import Callable

from algosdk.transaction import Transaction
from beaker.consts import algo
from websockets.legacy.client import connect

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    SigningAddress,
    EncryptionAddress,
    AlgoPublicKeys,
)
from oysterpack.algorand.client.model import MicroAlgos, AppId, Address
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.algorand.messaging.secure_message_client import SecureMessageClient
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    SecureMessageWebsocketHandler,
)
from oysterpack.apps.wallet_connect.domain.activity import (
    AppActivityId,
    AppActivitySpec,
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
    App,
    WalletConnectServiceError,
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

    async def validate(self, txns: list[Transaction]):
        if self._validation_exception:
            raise self._validation_exception


app_admin_private_key = AlgoPrivateKey()


@dataclass(slots=True)
class WalletConnectServiceMock(WalletConnectService):
    account_has_subscription_: bool = True
    account_subscription_expired_: bool = False
    account_subscription_app_id: AppId = AppId(10)

    app_keys_registered_: bool = True
    app_registered_: bool = True
    app_enabled_: bool = True
    app_admin_: Address = app_admin_private_key.signing_address

    account_registered_: bool = True
    account_opted_in_app_: bool = True
    app_activity_registered_: bool = True
    app_activity_spec_: Callable[[AppActivityId], AppActivitySpec] | None = None
    authorize_transactions_: bool = True
    wallet_connected_error_: WalletConnectServiceError | None = None
    wallet_app_conn_public_keys_: AlgoPublicKeys | None = None

    async def app_keys_registered(
        self,
        app_id: AppId,
        signing_address: SigningAddress,
        encryption_address: EncryptionAddress,
    ) -> bool:
        await asyncio.sleep(0)
        return self.app_keys_registered_

    async def app(self, app_id: AppId) -> App | None:
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

    async def wallet_app_conn_public_keys(
        self,
        account: Address,
        app_id: AppId,
    ) -> AlgoPublicKeys | None:
        await asyncio.sleep(0)
        if self.wallet_connected_error_:
            raise self.wallet_connected_error_

        return self.wallet_app_conn_public_keys_

    async def account_app_id(self, account: Address) -> AppId | None:
        if not self.account_has_subscription_:
            return None

        return self.account_subscription_app_id

    async def account_subscription(
        self,
        account: Address,
    ) -> AccountSubscription | None:
        await asyncio.sleep(0)
        if not self.account_has_subscription_:
            return None

        if self.account_subscription_expired_:
            return AccountSubscription(
                account=account,
                app_id=self.account_subscription_app_id,
                expiration=datetime.now(UTC) - timedelta(days=1),
            )
        return AccountSubscription(
            account=account,
            app_id=self.account_subscription_app_id,
            expiration=datetime.now(UTC) + timedelta(days=7),
        )

    async def app_activity_spec(
        self,
        app_id: AppId,
        app_activity_id: AppActivityId,
    ) -> AppActivitySpec | None:
        if self.app_activity_spec_:
            return self.app_activity_spec_(app_activity_id)

        if not self.app_activity_registered_:
            return None

        return AppActivitySpecMock(
            activity_id=app_activity_id,
            name="name",
            description="description",
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
        self.sender_private_key = AlgoPrivateKey()
        self.recipient_private_key = AlgoPrivateKey()
        self.wallet = AlgoPrivateKey()

    async def test_single_transaction(self):
        logger = super().get_logger("test_single_transaction")

        # SETUP
        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[
                AuthorizeTransactionsHandler(
                    wallet_connect=WalletConnectServiceMock(
                        wallet_app_conn_public_keys_=self.wallet.public_keys
                    ),
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
            transactions=[txn],
            app_activity_id=AppActivityId(AppId(10)),
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
            transactions=[txn],
            app_activity_id=AppActivityId(AppId(10)),
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
                                self.assertEqual(
                                    expected_err_code, failure.code, failure.message
                                )

                                await asyncio.sleep(0)

        await run_test(
            name="app is not registered",
            multisig_service=WalletConnectServiceMock(),
            expected_err_code=AuthorizeTransactionsErrCode.WalletConnectAppDisconnected,
        )
        await run_test(
            name="app is not registered",
            multisig_service=WalletConnectServiceMock(
                app_registered_=False,
                wallet_app_conn_public_keys_=self.wallet.public_keys,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AppNotRegistered,
        )
        await run_test(
            name="signer not subscribed",
            multisig_service=WalletConnectServiceMock(
                account_has_subscription_=False,
                wallet_app_conn_public_keys_=self.wallet.public_keys,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AccountNotRegistered,
        )
        await run_test(
            name="signer subscription expired",
            multisig_service=WalletConnectServiceMock(
                account_subscription_expired_=True,
                wallet_app_conn_public_keys_=self.wallet.public_keys,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AccountSubscriptionExpired,
        )
        await run_test(
            name="account has no subscription",
            multisig_service=WalletConnectServiceMock(
                account_has_subscription_=False,
                wallet_app_conn_public_keys_=self.wallet.public_keys,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.AccountNotRegistered,
        )
        await run_test(
            name="app activity not registered",
            multisig_service=WalletConnectServiceMock(
                app_activity_registered_=False,
                wallet_app_conn_public_keys_=self.wallet.public_keys,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.InvalidAppActivityId,
        )
        await run_test(
            name="app activity validation failed",
            multisig_service=WalletConnectServiceMock(
                app_activity_spec_=lambda app_activity_id: AppActivitySpecMock(
                    activity_id=app_activity_id,
                    name="name",
                    description="description",
                    validation_exception=Exception("app activity validation failed"),
                ),
                wallet_app_conn_public_keys_=self.wallet.public_keys,
            ),
            expected_err_code=AuthorizeTransactionsErrCode.InvalidAppActivity,
        )


if __name__ == "__main__":
    unittest.main()
