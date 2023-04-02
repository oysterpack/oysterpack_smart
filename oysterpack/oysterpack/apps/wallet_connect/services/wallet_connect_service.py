"""
OysterPack WalletConnectService
"""
from oysterpack.algorand.client.accounts.private_key import SigningAddress, EncryptionAddress
from oysterpack.algorand.client.model import AppId, Address, TxnId
from oysterpack.apps.wallet_connect.domain.activity import AppActivityId, AppActivitySpec, TxnActivityId, \
    TxnActivitySpec
from oysterpack.apps.wallet_connect.messsages.authorize_transactions import AuthorizeTransactionsRequest
from oysterpack.apps.wallet_connect.protocols.wallet_connect_service import WalletConnectService, AccountSubscription


class OysterPackWalletConnectService(WalletConnectService):

    async def app_keys_registered(
            self,
            app_id: AppId,
            signing_address: SigningAddress,
            encryption_address: EncryptionAddress,
    ) -> bool:
        raise NotImplementedError

    async def app_registered(self, app_id: AppId) -> bool:
        raise NotImplementedError

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
