"""
Messages for signing Algorand transactions
"""
from dataclasses import dataclass, field
from enum import auto, StrEnum
from typing import ClassVar, Self, cast, Tuple

import msgpack  # type: ignore
from algosdk.encoding import is_valid_address
from algosdk.transaction import Transaction, MultisigTransaction, PaymentTxn
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import SigningAddress
from oysterpack.algorand.client.model import AppId, TxnId
from oysterpack.algorand.client.transactions import transaction_message_for_signing
from oysterpack.core.message import Serializable, MessageType

RequestId = ULID
Signature = bytes
Description = str


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
    # - each transaction should have a description that clearly explains what the transaction is doing
    transactions: list[Tuple[Transaction, Description]]

    # high-level description that describes the overall purpose for these transactions
    description: Description

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
            (self.description, "description"),
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

        if len(self.description.strip()) == 0:
            raise SignTransactionsFailure(
                code=ErrCode.InvalidMessage, message="description cannot be blank"
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
            description,
        ) = msgpack.unpackb(packed)

        try:
            return cls(
                app_id=app_id,
                signer=signer,
                transactions=[
                    (Transaction.undictify(txn), desc) for (txn, desc) in txns
                ],
                description=description,
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
                [(txn.dictify(), desc) for (txn, desc) in self.transactions],
                self.description,
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
    transactions: list[Tuple[MultisigTransaction, Description]]
    description: Description

    # service fee payment
    service_fee: PaymentTxn

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
            description,
            service_fee,
        ) = msgpack.unpackb(packed)

        return cls(
            app_id=app_id,
            signer=signer,
            multisig_signer=multisig_signer,
            transactions=[
                (MultisigTransaction.undictify(txn), desc) for (txn, desc) in txns
            ],
            description=description,
            service_fee=cast(PaymentTxn, PaymentTxn.undictify(service_fee)),
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
                [(txn.dictify(), desc) for (txn, desc) in self.transactions],
                self.description,
                self.service_fee.dictify(),
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
