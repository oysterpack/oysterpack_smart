"""
Messages for signing Algorand transactions
"""
from dataclasses import dataclass, field
from typing import ClassVar, Self

import msgpack  # type: ignore
from algosdk.transaction import Transaction
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import SigningAddress
from oysterpack.algorand.client.model import AppId, TxnId
from oysterpack.core.message import Serializable, MessageType

RequestId = ULID
Signature = bytes
ErrCode = ULID


@dataclass(slots=True)
class SignTransactionsRequest(Serializable):
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
        ) = msgpack.unpackb(packed)

        return cls(
            request_id=RequestId.from_bytes(request_id),
            app_id=app_id,
            signer=signer,
            transactions=[Transaction.undictify(txn) for txn in txns],
            description=description,
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
            )
        )


@dataclass(slots=True)
class SignTransactionsResult(Serializable):
    request_id: RequestId

    # will be empty if there was an error
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
        (request_id, transaction_ids) = msgpack.unpackb(packed)

        return cls(
            request_id=RequestId.from_bytes(request_id),
            transaction_ids=transaction_ids,
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """

        return msgpack.packb(
            (
                self.request_id.bytes,
                self.transaction_ids,
            )
        )


@dataclass(slots=True)
class SignTransactionsError(Exception, Serializable):
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
            code=ErrCode.from_bytes(code),
            message=message,
        )

    def pack(self) -> bytes:
        """
        serialize the message
        """

        return msgpack.packb(
            (
                self.request_id.bytes,
                self.code.bytes,
                self.message,
            )
        )
