"""
Messages for signing Algorand transactions
"""
from dataclasses import dataclass, field
from enum import auto, StrEnum
from typing import ClassVar, Self, Tuple

import msgpack  # type: ignore
from algosdk.encoding import is_valid_address
from algosdk.transaction import Transaction, MultisigTransaction

from oysterpack.algorand.client.accounts.private_key import SigningAddress
from oysterpack.algorand.client.model import AppId, TxnId
from oysterpack.algorand.client.transactions import transaction_message_for_signing
from oysterpack.apps.multisig_wallet_connect.domain.activity import (
    TxnActivityId,
    AppActivityId,
)
from oysterpack.core.message import Serializable, MessageType


@dataclass(slots=True)
class SignTransactionsRequest(Serializable):
    """
    App is requesting transactions to be signed.
    """

    # app that has submitted the request
    #
    # Notes
    # -----
    # - this message's packed bytes must be signed by the app's creator auth account
    app_id: AppId

    # account that is being requested to sign the transactions
    # - the signer account must be rekeyed to a multisig account that is registered with the
    #   OysterPack Multisig Wallet Connect service
    signer: SigningAddress

    # list of transactions to be signed
    # - each transaction is linked to an ActivityId
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
        required_fields = (
            (self.app_id, "app_id"),
            (self.signer, "signer"),
            (self.app_activity_id, "app_activity_id"),
        )
        for required_field, name in required_fields:
            if required_field is None:
                raise SignTransactionsFailure(
                    code=ErrCode.InvalidMessage, message=f"{name} is required"
                )

        if not is_valid_address(self.signer):
            raise SignTransactionsFailure(
                code=ErrCode.InvalidMessage, message="signer address is invalid"
            )

        if len(self.transactions) == 0:
            raise SignTransactionsFailure(
                code=ErrCode.InvalidMessage,
                message="at least 1 transaction is required",
            )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        """
        :raise SignTransactionsFailure: with code=ErrCode.InvalidMessage if unpacking the message fails
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
                signer=signer,
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
            raise SignTransactionsFailure(
                code=ErrCode.InvalidMessage, message=f"failed to unpack message: {err}"
            )

    def pack(self) -> bytes:
        """
        serialize the message
        """
        return msgpack.packb(
            (
                self.app_id,
                self.signer,
                [
                    (txn.dictify(), txn_activity_id.bytes)
                    for (txn, txn_activity_id) in self.transactions
                ],
                self.app_activity_id.bytes,
            )
        )


@dataclass(slots=True)
class SignTransactionsSuccess(Serializable):
    """
    Transactions were successfully signed and submitted to the Algorand network.
    """

    transaction_ids: list[TxnId]
    service_fee_txid: TxnId

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
        (
            transaction_ids,
            service_fee_txid,
        ) = msgpack.unpackb(packed)

        return cls(
            transaction_ids=transaction_ids,
            service_fee_txid=service_fee_txid,
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """

        return msgpack.packb(
            (
                self.transaction_ids,
                self.service_fee_txid,
            )
        )


class ErrCode(StrEnum):
    """
    Error codes
    """

    InvalidMessage = auto()
    # indicates account has insufficient ALGO funds to pay for service and transaction fees
    InsufficientAlgoBalance = auto()

    # app is not registered
    AppNotRegistered = auto()
    # signer is not registered
    SignerNotRegistered = auto()

    InvalidAppActivityId = auto()
    InvalidTxnActivityId = auto()
    AppActivityNotRegistered = auto()
    InvalidTxnActivity = auto()
    InvalidAppActivity = auto()

    # transaction was rejected
    RejectedBySigner = auto()
    # signer client is not connected
    SignerNotConnected = auto()

    # invalid signature
    InvalidSignature = auto()

    # request timed out
    Timeout = auto()
    # request failed for other unexpected reasons
    Failure = auto()


@dataclass(slots=True)
class SignTransactionsFailure(Exception, Serializable):
    """
    SignTransactionsFailure
    """

    code: ErrCode
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


@dataclass(slots=True)
class SignMultisigTransactionsMessage(Serializable):
    """
    App's SignTransactionsRequest is converted into a SignMultisigTransactionsMessage per multisig signer.

    (request_id, multisig_signer) form the unique message identifier.
    """

    app_id: AppId

    # maps to the signer from the original request
    signer: SigningAddress
    # refers to one of the underlying multisig accounts that is required to sign the transaction
    multisig_signer: SigningAddress
    transactions: list[Tuple[MultisigTransaction, TxnActivityId]]
    app_activity_id: AppActivityId

    MSG_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVZNHQYJD650JVEJV7DZPNC9"),
        init=False,
        repr=False,
    )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        (
            app_id,
            signer,
            multisig_signer,
            txns,
            app_activity_id,
        ) = msgpack.unpackb(packed)

        return cls(
            app_id=app_id,
            signer=signer,
            multisig_signer=multisig_signer,
            transactions=[
                (
                    MultisigTransaction.undictify(txn),
                    TxnActivityId.from_bytes(txn_activity_id),
                )
                for (txn, txn_activity_id) in txns
            ],
            app_activity_id=AppActivityId.from_bytes(app_activity_id),
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """
        return msgpack.packb(
            (
                self.app_id,
                self.signer,
                self.multisig_signer,
                [
                    (txn.dictify(), txn_activity_id.bytes)
                    for (txn, txn_activity_id) in self.transactions
                ],
                self.app_activity_id.bytes,
            )
        )

    def verify_signatures(self) -> bool:
        """
        :return: True when all required signatures have been collected and verified on all transactions
        """
        for (txn, desc) in self.transactions:
            if not txn.multisig.verify(
                transaction_message_for_signing(txn.transaction)
            ):
                return False
        return True
