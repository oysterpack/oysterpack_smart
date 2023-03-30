"""
MultisigService Protocol
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from oysterpack.algorand.client.model import Address, AppId, TxnId
from oysterpack.apps.multisig_wallet_connect.domain.activity import (
    AppActivityId,
    AppActivitySpec,
    TxnActivitySpec,
)
from oysterpack.apps.multisig_wallet_connect.messsages.authorize_transactions import (
    TxnActivityId,
    AuthorizeTransactionsRequest,
)


@dataclass(slots=True, frozen=True)
class App:
    """
    App that is registered with the multisig sevice
    """

    app_id: AppId
    # While the app is disabled the service will not be able to use the multisig service.
    # This mechanism is put in place to protect accounts. For example, an app may be disabled if a contract exploit was
    # discovered.
    enabled: bool


@dataclass(slots=True, frozen=True)
class AccountSubscription:
    """
    Account Subscription
    """

    account: Address

    # blockchain timestamp - which differs from wall clock time
    expiration: datetime
    blockchain_timestamp: datetime

    @property
    def expired(self) -> bool:
        return self.expiration < self.blockchain_timestamp


class MultisigServiceError(Exception):
    """
    MultisigService base exception
    """


class AuthorizerOffline(MultisigServiceError):
    """
    Authorizer is currently offline
    """


class MultisigService(Protocol):
    """
    MultisigService
    """

    async def app_registered(self, app_id: AppId) -> bool:
        """
        :param app_id: AppId
        :return: True if the app is registered with the service
        """
        ...

    async def account_registered(self, account: Address, app_id: AppId) -> bool:
        """
        In order for an account to receive transactions through the multisig service, the account must be opted into
        the multisig service and the app.

        If an account opts out of the multisig service, then the account effectively disables the multisig service.
        Even though the account may still be opted into apps, they will stop receiving transactions.

        :param account: Address
        :param app_id: AppId
        :return: True if the account has opted into the multisig service and the app
        """
        ...

    async def get_account_subscription(
        self, account: Address
    ) -> AccountSubscription | None:
        """
        Note
        ----
        Even if the account has a subscription, it may have expired.

        :return: None if the account has no subscription.
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

    def get_app_activity_spec(
        self,
        app_activity_id: AppActivityId,
    ) -> AppActivitySpec | None:
        """
        Looks up the AppActivitySpec for the specified AppActivityId
        """
        ...

    def get_txn_activity_spec(
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
