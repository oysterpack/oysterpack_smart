"""
Standardized messaging format using MessagePack as the binary serialization format.

https://msgpack.org/
"""
from dataclasses import dataclass, field
from typing import Self, Protocol, ClassVar, cast

import msgpack  # type: ignore
from algosdk import encoding
from algosdk.transaction import Multisig
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import (
    SigningAddress,
    AlgoPrivateKey,
    verify_message,
)


class MessageId(ULID):
    """
    Unique message ID
    """


class MessageType(ULID):
    """
    Message type ID
    """


MessageData = bytes
Signature = bytes


class Serializable(Protocol):
    """
    Serializable protocol
    """

    @classmethod
    def message_type(cls) -> MessageType:
        ...

    def pack(self) -> bytes:
        """
        Packs the object into bytes
        """
        ...

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        """
        Unpacks the packed bytes into a new instance of Self
        """
        ...


@dataclass(slots=True)
class Message:
    """
    Message

    :field:`id` - unique message ID
    :field:`type` - data message type
    :field:`data` - msgpack serialized data
    """

    msg_id: MessageId
    msg_type: MessageType
    data: MessageData

    @classmethod
    def create(cls, msg_type: MessageType, data: bytes) -> Self:
        """
        Constructs a new Message with an autogenerated message ID
        """
        return cls(
            msg_id=MessageId(),
            msg_type=msg_type,
            data=data,
        )

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        """
        deserializes the message
        """
        (msg_type, msg_id, data) = msgpack.unpackb(packed, use_list=False)
        return cls(
            msg_id=MessageId.from_bytes(msg_id),
            msg_type=MessageType.from_bytes(msg_type),
            data=data,
        )

    def pack(self) -> bytes:
        """
        Serialize the message

        Notes
        -----
        - serialized message format: (MessageId, MessageType, MessageData)
        """
        return msgpack.packb(
            (
                self.msg_type.bytes,
                self.msg_id.bytes,
                self.data,
            )
        )


@dataclass(slots=True)
class SignedMessage(Serializable):
    """
    Signed message
    """

    signer: SigningAddress
    signature: Signature

    data: MessageData
    msg_type: MessageType

    _MESSAGE_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVS4P3NQY9BDXH7X9MN17A6X"),
        init=False,
        repr=False,
    )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls._MESSAGE_TYPE

    @classmethod
    def sign(
        cls,
        private_key: AlgoPrivateKey,
        data: MessageData,
        msg_type: MessageType,
    ) -> Self:
        """
        Signs the encrypted message
        """
        return cls(
            signer=private_key.signing_address,
            signature=private_key.sign(data).signature,
            data=data,
            msg_type=msg_type,
        )

    def verify(self) -> bool:
        """
        :return: True if the message signature passed verification
        """
        return verify_message(
            message=self.data,
            signature=self.signature,
            signer=self.signer,
        )

    @classmethod
    def unpack(cls, msg: bytes) -> Self:
        """
        Deserialize the msg
        """
        (
            msg_type,
            signer,
            signature,
            data,
        ) = msgpack.unpackb(msg, use_list=False)

        return cls(
            signer=signer,
            signature=signature,
            data=data,
            msg_type=MessageType.from_bytes(msg_type),
        )

    def pack(self) -> bytes:
        """
        Serialized the message into bytes
        """
        return msgpack.packb(
            (
                self.msg_type.bytes,
                self.signer,
                self.signature,
                self.data,
            )
        )


class MultisigSignaturesBelowThreshold(Exception):
    """
    The number of signatures is below the required threshold
    """


@dataclass(slots=True)
class MultisigMessage(Serializable):
    """
    Message signed by a multisig account
    """

    multisig: Multisig

    data: MessageData
    msg_type: MessageType

    _MESSAGE_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVXYW3CASBFM99X65KAPJ8JT"),
        init=False,
        repr=False,
    )

    def __post_init__(self):
        self.multisig.validate()

    @classmethod
    def message_type(cls) -> MessageType:
        return cls._MESSAGE_TYPE

    @classmethod
    def unpack(cls, msg: bytes) -> Self:
        """
        Deserialize the msg
        """
        (
            msg_type,
            multisig_version,
            multisig_threshold,
            multisig_subsigs,
            data,
        ) = msgpack.unpackb(msg, use_list=False)
        multisig = Multisig(
            version=multisig_version,
            threshold=multisig_threshold,
            addresses=[
                encoding.encode_address(public_key)
                for (public_key, _signature) in multisig_subsigs
            ],
        )
        for i, subsig in enumerate(multisig.subsigs):
            subsig.signature = multisig_subsigs[i][1]
        return cls(
            multisig=multisig,
            data=data,
            msg_type=MessageType.from_bytes(msg_type),
        )

    def pack(self) -> bytes:
        """
        Serialized the message into bytes
        """
        return msgpack.packb(
            (
                self.msg_type.bytes,
                self.multisig.version,
                self.multisig.threshold,
                [
                    (subsig.public_key, subsig.signature)
                    for subsig in self.multisig.subsigs
                ],
                self.data,
            )
        )

    def verify(self) -> bool:
        """
        :return: True if the message signature passed verification
        """
        subsigs = [
            subsig for subsig in self.multisig.subsigs if subsig.signature is not None
        ]
        if len(subsigs) < self.multisig.threshold:
            raise MultisigSignaturesBelowThreshold

        for subsig in subsigs:
            if not verify_message(
                message=self.data,
                signature=subsig.signature,
                signer=cast(SigningAddress, encoding.encode_address(subsig.public_key)),
            ):
                return False

        return True

    def __eq__(self, other) -> bool:
        if not isinstance(other, MultisigMessage):
            return False

        if self.data != other.data:
            return False

        if self.msg_type != other.msg_type:
            return False

        if self.multisig.version != other.multisig.version:
            return False

        if self.multisig.threshold != other.multisig.threshold:
            return False

        if len(self.multisig.subsigs) != len(other.multisig.subsigs):
            return False

        for subsig_1, subsig_2 in zip(self.multisig.subsigs, other.multisig.subsigs):
            if subsig_1.public_key != subsig_2.public_key:
                return False
            if subsig_1.signature != subsig_2.signature:
                return False

        return True

    def __repr__(self):
        return f"MultisigMessageData(multisig={self.multisig.dictify()}, msg_type={self.msg_type}, data={self.data})"
