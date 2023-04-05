"""
OysterPack WalletConnectService
"""
import asyncio
import base64
from concurrent.futures.thread import ThreadPoolExecutor
from typing import cast, Any

from algosdk.encoding import decode_address, encode_address
from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient
from beaker.client import ApplicationClient

from oysterpack.algorand.client.accounts.private_key import (
    SigningAddress,
    EncryptionAddress,
)
from oysterpack.algorand.client.model import AppId, Address, TxnId
from oysterpack.apps.wallet_connect.contracts import wallet_connect_app
from oysterpack.apps.wallet_connect.domain.activity import (
    AppActivityId,
    AppActivitySpec,
    TxnActivityId,
    TxnActivitySpec,
)
from oysterpack.apps.wallet_connect.messsages.authorize_transactions import (
    AuthorizeTransactionsRequest,
)
from oysterpack.apps.wallet_connect.protocols.wallet_connect_service import (
    WalletConnectService,
    AccountSubscription,
    App,
    WalletConnectServiceError,
    AppNotRegistered,
)


class OysterPackWalletConnectService(WalletConnectService):
    def __init__(
        self,
        wallet_connect_service_app_id: AppId,
        executor: ThreadPoolExecutor,
        algod_client: AlgodClient,
    ):
        self._wallet_connect_service_app_id = AppId(wallet_connect_service_app_id)
        self.__executor = executor
        self.__algod_client = algod_client

    @property
    def wallet_connect_service_app_id(self) -> AppId:
        return self._wallet_connect_service_app_id

    async def app_keys_registered(
        self,
        app_id: AppId,
        signing_address: SigningAddress,
        encryption_address: EncryptionAddress,
    ) -> bool:
        if not await self.app_registered(app_id):
            raise AppNotRegistered()

        def _app_keys_registered() -> bool:
            try:
                box = self.__algod_client.application_box_by_name(
                    application_id=app_id,
                    box_name=decode_address(signing_address),
                )
                return (
                    encode_address(base64.b64decode(cast(dict[str, Any], box)["value"]))
                    == encryption_address
                )
            except AlgodHTTPError as err:
                if err.code == 404:
                    return False
                raise

        return await asyncio.get_event_loop().run_in_executor(
            self.__executor, _app_keys_registered
        )

    async def app_registered(self, app_id: AppId) -> bool:
        def _app_registered():
            try:
                # app must be created by the WalletConnectService app
                app_info = cast(
                    dict[str, Any], self.__algod_client.application_info(app_id)
                )
                return (
                    app_info["params"]["creator"]
                    == self._wallet_connect_service_app_id.to_address()
                )
            except AlgodHTTPError as err:
                if err.code == 404:
                    return False
                raise WalletConnectServiceError() from err

        return await asyncio.get_event_loop().run_in_executor(
            self.__executor, _app_registered
        )

    async def lookup_app(self, app_id: AppId) -> App | None:
        if not await self.app_registered(app_id):
            return None

        def _lookup_app():
            try:
                app_client = ApplicationClient(
                    self.__algod_client,
                    app_id=app_id,
                    app=wallet_connect_app.app,
                )
                global_state = app_client.get_global_state()
                return App(
                    app_id=app_id,
                    name=cast(str, global_state["name"]),
                    url=cast(str, global_state["url"]),
                    enabled=global_state["enabled"] == 1,
                    admin=Address(cast(str, global_state["admin"])),
                )

            except AlgodHTTPError as err:
                if err.code == 404:
                    return None
                raise WalletConnectServiceError() from err

        return await asyncio.get_event_loop().run_in_executor(
            self.__executor, _lookup_app
        )

    async def get_account_subscription(
        self, account: Address
    ) -> AccountSubscription | None:
        raise NotImplementedError

    async def account_opted_in_app(self, account: Address, app_id: AppId) -> bool:
        raise NotImplementedError

    async def wallet_connected(self, account: Address, app_id: AppId) -> bool:
        raise NotImplementedError

    async def app_activity_registered(
        self,
        app_id: AppId,
        app_activity_id: AppActivityId,
    ) -> bool:
        raise NotImplementedError

    def get_app_activity_spec(
        self,
        app_activity_id: AppActivityId,
    ) -> AppActivitySpec | None:
        raise NotImplementedError

    def get_txn_activity_spec(
        self,
        txn_activity_id: TxnActivityId,
    ) -> TxnActivitySpec | None:
        raise NotImplementedError

    async def authorize_transactions(
        self, request: AuthorizeTransactionsRequest
    ) -> bool:
        raise NotImplementedError

    async def sign_transactions(
        self, request: AuthorizeTransactionsRequest
    ) -> list[TxnId]:
        raise NotImplementedError
