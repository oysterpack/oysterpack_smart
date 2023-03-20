"""
Messages for signing Algorand transactions
"""
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import ClassVar, Self, cast

import msgpack  # type: ignore
from algosdk.transaction import Transaction, MultisigTransaction, PaymentTxn
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import SigningAddress
from oysterpack.algorand.client.model import AppId, TxnId
from oysterpack.algorand.client.transactions import transaction_message_for_signing
from oysterpack.core.message import Serializable, MessageType

RequestId = ULID
Signature = bytes


@dataclass(slots=True)
class SignTransactionsRequest(Serializable):
    """
    App is requesting transactions to be signed.
    """

    # unique request ID
    request_id: RequestId

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
    #
    # TODO: standardize transaction notes
    # - transaction notes should be used to describe what each transaction is doing
    # - application method call notes should include the method call and args in a standardized format
    transactions: list[Transaction]

    # human-readable high-level description that describes the overall purpose for these transactions
    # What action is being taken?
    description: str

    # service fee payment
    service_fee: PaymentTxn

    MSG_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVXV7CQQY4Q0SSW6GBJCN192"),
        init=False,
        repr=False,
    )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        (
            request_id,
            app_id,
            signer,
            txns,
            description,
            service_fee,
        ) = msgpack.unpackb(packed)

        return cls(
            request_id=RequestId.from_bytes(request_id),
            app_id=app_id,
            signer=signer,
            transactions=[Transaction.undictify(txn) for txn in txns],
            description=description,
            service_fee=cast(PaymentTxn, PaymentTxn.undictify(service_fee)),
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """
        return msgpack.packb(
            (
                self.request_id.bytes,
                self.app_id,
                self.signer,
                [txn.dictify() for txn in self.transactions],
                self.description,
                self.service_fee.dictify(),
            )
        )


@dataclass(slots=True)
class SignTransactionsResult(Serializable):
    """
    Transactions were succesfully signed and submitted to the Algorand network.
    """

    # correlates back to the request
    request_id: RequestId

    # will be empty if there was an error
    transaction_ids: list[TxnId]

    # service fee payment
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
            request_id,
            transaction_ids,
            service_fee_txid,
        ) = msgpack.unpackb(packed)

        return cls(
            request_id=RequestId.from_bytes(request_id),
            transaction_ids=transaction_ids,
            service_fee_txid=service_fee_txid,
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """

        return msgpack.packb(
            (self.request_id.bytes, self.transaction_ids, self.service_fee_txid)
        )


@dataclass(slots=True)
class SignMultisigTransactionsMessage(Serializable):
    """
    App's SignTransactionsRequest is converted into a SignMultisigTransactionsMessage per multisig signer.

    (request_id, multisig_signer) form the unique message identifier.
    """

    request_id: RequestId
    app_id: AppId

    # maps to the signer from the original request
    signer: SigningAddress
    # refers to one of the underlying multisig accounts that is required to sign the transaction
    multisig_signer: SigningAddress
    transactions: list[MultisigTransaction]
    description: str

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
            request_id,
            app_id,
            signer,
            multisig_signer,
            txns,
            description,
            service_fee,
        ) = msgpack.unpackb(packed)

        return cls(
            request_id=RequestId.from_bytes(request_id),
            app_id=app_id,
            signer=signer,
            multisig_signer=multisig_signer,
            transactions=[MultisigTransaction.undictify(txn) for txn in txns],
            description=description,
            service_fee=cast(PaymentTxn, PaymentTxn.undictify(service_fee)),
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """
        return msgpack.packb(
            (
                self.request_id.bytes,
                self.app_id,
                self.signer,
                self.multisig_signer,
                [txn.dictify() for txn in self.transactions],
                self.description,
                self.service_fee.dictify(),
            )
        )

    def verify_signatures(self) -> bool:
        """
        :return: True when all required signatures have been collected and verified on all transactions
        """
        for txn in self.transactions:
            if not txn.multisig.verify(
                transaction_message_for_signing(txn.transaction)
            ):
                return False
        return True


class ErrCode(IntEnum):
    # app is not registered
    AppNotRegistered = auto()
    # signer is not registered
    SignerNotRegistered = auto()
    # No service payment was attached
    NoServicePaymentAttached = auto()

    # transaction was rejected
    Rejected = auto()
    # request timed out
    Timeout = auto()
    # invalid signature
    InvalidSignature = auto()
    # signer not available
    SignerNotAvailable = auto()

    # request failed for other unexpected reasons
    Failure = auto()


@dataclass(slots=True)
class SignTransactionsError(Exception, Serializable):
    """
    The SignTransactionsRequest failed
    """

    request_id: RequestId
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
        (request_id, code, message) = msgpack.unpackb(packed)

        return cls(
            request_id=RequestId.from_bytes(request_id),
            code=code,
            message=message,
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """

        return msgpack.packb(
            (
                self.request_id.bytes,
                self.code,
                self.message,
            )
        )
