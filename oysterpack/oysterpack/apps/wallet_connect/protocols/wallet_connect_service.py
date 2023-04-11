"""
MultisigService Protocol
"""
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Protocol

from oysterpack.algorand.client.accounts.private_key import (
    SigningAddress,
    EncryptionAddress,
    AlgoPublicKeys,
)
from oysterpack.algorand.client.model import Address, AppId, TxnId
from oysterpack.apps.wallet_connect.domain.activity import (
    AppActivityId,
    AppActivitySpec,
    TxnActivitySpec,
)
from oysterpack.apps.wallet_connect.messsages.authorize_transactions import (
    TxnActivityId,
    AuthorizeTransactionsRequest,
)


@dataclass(slots=True, frozen=True)
class App:
    """
    App that is registered with the wallet connect service
    """

    app_id: AppId

    name: str
    url: str

    # While the app is disabled the service will not be able to use the wallet connect service.
    # This mechanism is put in place to protect accounts. For example, an app may be disabled
    # if a contract exploit was discovered.
    enabled: bool

    admin: Address


@dataclass(slots=True, frozen=True)
class AccountSubscription:
    """
    Account Subscription
    """

    account: Address
    # WalletConnectAccount app ID
    app_id: AppId

    expiration: datetime

    @property
    def expired(self) -> bool:
        return self.expiration < datetime.now(UTC)


class WalletConnectServiceError(Exception):
    """
    WalletConnectService base exception
    """


class AppNotRegistered(WalletConnectServiceError):
    """
    App is not registered
    """


class AppDisabled(WalletConnectServiceError):
    """
    App is registered but is disabled
    """


class AccountNotRegistered(WalletConnectServiceError):
    """
    Account is unknown, i.e., it is not subscribed with the wallet connect service
    """


class AccountSubscriptionExpired(WalletConnectServiceError):
    """
    Account has not subscribed to the service
    """


class AccountNotOptedIntoApp(WalletConnectServiceError):
    """
    Account has not opted into the app
    """


class InvalidWalletPublickeys(WalletConnectServiceError):
    """
    Wallet public keys are not registered with the specified account
    """


class WalletOffline(WalletConnectServiceError):
    """
    Wallet is currently offline
    """


class WalletConnectService(Protocol):
    """
    MultisigService
    """

    async def app_registered(self, app_id: AppId) -> bool:
        """
        :param app_id: AppId
        :return: True if the app is registered
        """
        ...

    async def app_keys_registered(
        self,
        app_id: AppId,
        signing_address: SigningAddress,
        encryption_address: EncryptionAddress,
    ) -> bool:
        """
        :return: True if the signing and encrptuion addresses are registered with the service
        :raises AppNotRegistered: If app is not registered
        """
        ...

    async def app(self, app_id: AppId) -> App | None:
        """
        :param app_id: AppId
        :return: None if the app is not registered
        """
        ...

    async def account_app_id(self, account: Address) -> AppId | None:
        """
        Looks up the WalletConnectAccount app ID for the specified account

        :param account:  Address
        :return: None if the account is not registered
        """

    async def account_subscription(
        self, account: Address
    ) -> AccountSubscription | None:
        """
        Note
        ----
        Even if the account has a subscription, it may have expired.

        :return: None if the account has no subscription.
        """
        ...

    async def account_opted_in_app(self, account: Address, app_id: AppId) -> bool:
        """
        :param account: Address
        :param app_id: AppId
        :return: True if the account has opted into the app
        """
        ...

    async def wallet_connected(
        self, account: Address, app_id: AppId, wallet_public_keys: AlgoPublicKeys
    ) -> bool:
        """
        :param account: Address
        :param app_id: AppId
        :return: True if the wallet is connected to the app using the specified wallet public keys

        :raises AppNotRegistered: if the app is not registered with the service
        :raises AccountNotRegistered: if the account is not currently subscribed
        :raises AccountNotOptedIntoApp: if the account has not opted into the app
        :raises AccountSubscriptionExpired: if the account subscription is expired
        :raises InvalidWalletPublickeys: If wallet public keys are not registered with the specified account
        """
        ...

    async def app_activity_registered(
        self,
        app_id: AppId,
        app_activity_id: AppActivityId,
    ) -> bool:
        """
        Returns false if the app activity is not registered.
        """
        ...

    def app_activity_spec(
        self,
        app_activity_id: AppActivityId,
    ) -> AppActivitySpec | None:
        """
        Looks up the AppActivitySpec for the specified AppActivityId
        """
        ...

    def txn_activity_spec(
        self,
        txn_activity_id: TxnActivityId,
    ) -> TxnActivitySpec | None:
        """
        Looks up the TxnActivitySpec for the specified TxnActivityId
        """
        ...

    async def authorize_transactions(
        self, request: AuthorizeTransactionsRequest
    ) -> bool:
        """
        Transactions are sent to the user for authorization, i.e., either approve or reject

        :return: True is the transactions are approved. False indicates the transactions are rejected.
        """
        ...

    async def sign_transactions(
        self, request: AuthorizeTransactionsRequest
    ) -> list[TxnId]:
        """
        Signs the transactions and submits them to Algorand.

        :return: list of Algorand transaction IDs that can be used to track transaction status
        """
        ...
