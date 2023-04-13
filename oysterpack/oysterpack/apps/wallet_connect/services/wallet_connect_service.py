"""
OysterPack WalletConnectService
"""
import asyncio
import base64
from base64 import b64decode
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime, UTC
from typing import cast, Any

import algosdk
from algosdk.encoding import decode_address, encode_address
from algosdk.error import AlgodHTTPError
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from beaker.client import ApplicationClient

from oysterpack.algorand.client.accounts.private_key import (
    SigningAddress,
    EncryptionAddress,
    AlgoPublicKeys,
)
from oysterpack.algorand.client.model import AppId, Address, TxnId
from oysterpack.apps.wallet_connect.contracts import (
    wallet_connect_app,
    wallet_connect_account,
)
from oysterpack.apps.wallet_connect.contracts.wallet_connect_account import (
    WalletConnectAccountState,
)
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
            self.__executor,
            _app_keys_registered,
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
            self.__executor,
            _app_registered,
        )

    async def app(self, app_id: AppId) -> App | None:
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
            self.__executor,
            _lookup_app,
        )

    async def account_app_id(self, account: Address) -> AppId | None:
        def _account_app_id() -> AppId | None:
            address_type = algosdk.abi.AddressType()
            try:
                result = self.__algod_client.application_box_by_name(
                    application_id=self._wallet_connect_service_app_id,
                    box_name=address_type.encode(account),
                )
            except AlgodHTTPError as err:
                if err.code == 404:
                    return None
                raise WalletConnectServiceError() from err

            box_contents = b64decode(cast(dict[str, Any], result)["value"])
            uint64_type = algosdk.abi.UintType(64)
            return AppId(uint64_type.decode(box_contents))

        return await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            _account_app_id,
        )

    async def account_subscription(
        self,
        account: Address,
    ) -> AccountSubscription | None:
        def _account_subscription() -> AccountSubscription | None:
            address_type = algosdk.abi.AddressType()
            try:
                result = self.__algod_client.application_box_by_name(
                    self._wallet_connect_service_app_id,
                    address_type.encode(account),
                )
            except AlgodHTTPError as err:
                if err.code == 404:
                    return None
                raise WalletConnectServiceError() from err

            app_id_type = algosdk.abi.UintType(64)
            box_contents = b64decode(cast(dict[str, Any], result)["value"])
            app_id = app_id_type.decode(box_contents)

            app_client = ApplicationClient(
                self.__algod_client,
                app=wallet_connect_account.application,
                app_id=app_id,
            )
            expiration = app_client.get_global_state()[
                WalletConnectAccountState.expiration.str_key()
            ]
            return AccountSubscription(
                account=account,
                app_id=AppId(app_id),
                expiration=datetime.fromtimestamp(cast(int, expiration), UTC),
            )

        return await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            _account_subscription,
        )

    async def account_opted_in_app(self, account: Address, app_id: AppId) -> bool:
        account_app_id = await self.account_app_id(account)
        if account_app_id is None:
            return False

        def _account_opted_in_app():
            try:
                self.__algod_client.account_application_info(
                    address=get_application_address(account_app_id),
                    application_id=app_id,
                )
                return True
            except AlgodHTTPError as err:
                if err.code == 404:
                    return False
                raise WalletConnectServiceError() from err

        return await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            _account_opted_in_app,
        )

    async def wallet_app_conn_public_keys(
        self,
        account: Address,
        app_id: AppId,
    ) -> AlgoPublicKeys | None:
        def _wallet_app_conn_public_keys():
            uint64_type = algosdk.abi.UintType(64)
            try:
                result = self.__algod_client.application_box_by_name(
                    application_id=app_id,
                    box_name=uint64_type.encode(app_id),
                )
            except AlgodHTTPError as err:
                if err.code == 404:
                    return None
                raise WalletConnectServiceError() from err

            box_contents = b64decode(cast(dict[str, Any], result)["value"])
            wallet_public_keys_tuple = algosdk.abi.TupleType(
                [
                    algosdk.abi.AddressType(),
                    algosdk.abi.AddressType(),
                ]
            )
            keys = wallet_public_keys_tuple.decode(box_contents)
            return AlgoPublicKeys(
                signing_address=keys[0],
                encryption_address=keys[1],
            )

        return await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            _wallet_app_conn_public_keys,
        )

    async def app_activity_registered(
        self,
        app_id: AppId,
        app_activity_id: AppActivityId,
    ) -> bool:
        raise NotImplementedError

    def app_activity_spec(
        self,
        app_activity_id: AppActivityId,
    ) -> AppActivitySpec | None:
        raise NotImplementedError

    def txn_activity_spec(
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
