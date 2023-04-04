"""
Messages for signing Algorand transactions
"""
from dataclasses import dataclass, field
from enum import auto, StrEnum
from typing import ClassVar, Self, Tuple

import msgpack  # type: ignore
from algosdk import transaction, constants
from algosdk.encoding import is_valid_address
from algosdk.transaction import Transaction

from oysterpack.algorand.client.accounts.private_key import SigningAddress
from oysterpack.algorand.client.model import AppId, TxnId
from oysterpack.apps.wallet_connect.domain.activity import (
    TxnActivityId,
    AppActivityId,
)
from oysterpack.core.message import Serializable, MessageType


@dataclass(slots=True)
class AuthorizeTransactionsRequest(Serializable):
    """
    App is requesting transactions to be signed.
    """

    # app that has submitted the request
    #
    # Notes
    # -----
    # - this message's packed bytes must be signed by the app's creator auth account
    app_id: AppId

    # account that is being requested to authorize the transactions
    authorizer: SigningAddress

    # list of transactions to be signed
    # - each transaction is linked to an ActivityId
    # - all transactions must be contained with a single atomic transaction group,
    #   which limits the max number of transactions to 16
    transactions: list[Tuple[Transaction, TxnActivityId]]

    # Activity that is assigned to the set of transactions
    app_activity_id: AppActivityId

    MSG_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVXV7CQQY4Q0SSW6GBJCN192"),
        init=False,
        repr=False,
    )

    def __post_init__(self):
        """
        Performs basic validation

        :raise SignTransactionsFailure: with ode=ErrCode.InvalidMessage
        """

        def check_required_fields():
            required_fields = (
                (self.app_id, "app_id"),
                (self.authorizer, "authorizer"),
                (self.app_activity_id, "app_activity_id"),
            )
            for required_field, name in required_fields:
                if required_field is None:
                    raise AuthorizeTransactionsError(
                        code=AuthorizeTransactionsErrCode.InvalidMessage,
                        message=f"{name} is required",
                    )

        def check_signer_address():
            if not is_valid_address(self.authorizer):
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.InvalidMessage,
                    message="signer address is invalid",
                )

        def check_transaction_count():
            if not 1 <= len(self.transactions) <= constants.tx_group_limit:
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.InvalidMessage,
                    message=f"Number of transactions must be 1-{constants.tx_group_limit}",
                )

        def check_transaction_group_id():
            if len(self.transactions) == 1:
                # if there is only 1 transaction, then a group ID is not required
                return

            for tx, _activity_id in self.transactions:
                if tx.group is None:
                    raise AuthorizeTransactionsError(
                        code=AuthorizeTransactionsErrCode.InvalidMessage,
                        message="all transactions must have a group ID",
                    )

            group_ids = {txn.group for (txn, _activity_id) in self.transactions}
            if len(group_ids) > 1:
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.InvalidMessage,
                    message="all transactions must have the same group ID, i.e., executed atomically",
                )

            txns = [txn for txn, _ in self.transactions]
            # strip group ID in order to recalculate it
            for txn in txns:
                txn.group = None
            group_id = transaction.calculate_group_id(txns)
            if group_id not in group_ids:
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.InvalidMessage,
                    message="computed group ID does not match assigned group ID",
                )
            # reassign the group ID
            for txn in txns:
                txn.group = group_id

        check_required_fields()
        check_signer_address()
        check_transaction_count()
        check_transaction_group_id()

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        """
        :raise SignTransactionsError: with code=ErrCode.InvalidMessage if unpacking the message fails
        """
        (
            app_id,
            signer,
            txns,
            app_activity_id,
        ) = msgpack.unpackb(packed)

        try:
            return cls(
                app_id=app_id,
                authorizer=signer,
                transactions=[
                    (
                        Transaction.undictify(txn),
                        TxnActivityId.from_bytes(txn_activity_id),
                    )
                    for (txn, txn_activity_id) in txns
                ],
                app_activity_id=AppActivityId.from_bytes(app_activity_id),
            )
        except Exception as err:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.InvalidMessage,
                message=f"failed to unpack message: {err}",
            )

    def pack(self) -> bytes:
        return msgpack.packb(
            (
                self.app_id,
                self.authorizer,
                [
                    (txn.dictify(), txn_activity_id.bytes)
                    for (txn, txn_activity_id) in self.transactions
                ],
                self.app_activity_id.bytes,
            )
        )


@dataclass(slots=True)
class AuthorizeTransactionsRequestAccepted(Serializable):
    """
    Used to reply back to the app to acknowledge that the request has passed validation and has been accepted.

    The request will be forwarded to the user to authorize the transactions.
    """

    MSG_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GWHFWY29F1PYBXFVECKK480K"),
        init=False,
        repr=False,
    )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        return cls()

    def pack(self) -> bytes:
        return msgpack.packb(None)


@dataclass(slots=True)
class AuthorizeTransactionsSuccess(Serializable):
    """
    Transactions were successfully signed and submitted to the Algorand network.
    """

    transaction_ids: list[TxnId]

    MSG_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVY34DVXW4RBZ75DSDZTXCTX"),
        init=False,
        repr=False,
    )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        transaction_ids = msgpack.unpackb(packed)
        return cls(transaction_ids)

    def pack(self) -> bytes:
        return msgpack.packb(self.transaction_ids)


class AuthorizeTransactionsErrCode(StrEnum):
    """
    Error codes
    """

    # Indicates a message was received using unregistered keys
    UnauthorizedMessage = auto()
    InvalidMessage = auto()
    # indicates account has insufficient ALGO funds to pay for service and transaction fees
    InsufficientAlgoBalance = auto()

    # app is not registered
    AppNotRegistered = auto()
    AppDisabled = auto()
    # account is not opted in with the wallet connect service
    AccountNotRegistered = auto()
    # account has not opted into the app
    AccountNotOptedIntoApp = auto()
    # account is opted in with the wallet connect service, but its subscription has expired
    AccountSubscriptionExpired = auto()
    # wallet is not connected to the app
    WalletConnectAppDisconnected = auto()

    InvalidAppActivityId = auto()
    InvalidTxnActivityId = auto()
    AppActivityNotRegistered = auto()
    InvalidTxnActivity = auto()
    InvalidAppActivity = auto()

    # transaction was rejected
    Rejected = auto()
    # signer client is not connected
    WalletNotConnected = auto()

    # invalid signature
    InvalidSignature = auto()

    # request timed out
    Timeout = auto()
    # request failed for other unexpected reasons
    Failure = auto()


@dataclass(slots=True)
class AuthorizeTransactionsFailure(Serializable):
    """
    SignTransactionsFailure

    Notes
    -----
    - This class purposely does not extend Exception because it causes pickling to fail (reason unknown).
      - pickling is required because all messages are packed and encrypted in a separate process to offload the
        CPU work and not block the event loop
    """

    code: AuthorizeTransactionsErrCode
    message: str

    MSG_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVY3EEAY6DVYPE1YSFCY8G0C"),
        init=False,
        repr=False,
    )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        (code, message) = msgpack.unpackb(packed)

        return cls(code=code, message=message)

    def pack(self) -> bytes:
        """
        serialize the message
        """

        return msgpack.packb(
            (
                self.code,
                self.message,
            )
        )

    def __str__(self):
        return f"SignTransactionFailure [{self.code}] {self.message}"


@dataclass(slots=True)
class AuthorizeTransactionsError(Exception):
    """
    SignTransactionsError
    """

    code: AuthorizeTransactionsErrCode
    message: str

    def to_failure(self) -> AuthorizeTransactionsFailure:
        return AuthorizeTransactionsFailure(code=self.code, message=self.message)
