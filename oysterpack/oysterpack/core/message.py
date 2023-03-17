"""
Standardized messaging format
"""
from dataclasses import dataclass

import msgpack  # type: ignore
from ulid import ULID


class MessageId(ULID):
    """
    Unique message ID
    """


class MessageType(ULID):
    """
    Message type ID
    """


@dataclass(slots=True)
class Message:
    """
    Message

    :field:`id` - unique message ID
    :field:`type` - message type
    :field:`data` - msgpack serialization format
    """

    id: MessageId
    type: MessageType
    data: bytes

    @classmethod
    def create(cls, msg_type: MessageType, data: bytes) -> "Message":
        """
        Constructor
        """
        return cls(
            id=MessageId(),
            type=msg_type,
            data=data,
        )

    @classmethod
    def unpack(cls, packed: bytes) -> "Message":
        """
        deserializes the message
        """
        (id, type, data) = msgpack.unpackb(packed, use_list=False)
        return cls(
            id=MessageId.from_bytes(id),
            type=MessageType.from_bytes(type),
            data=data,
        )

    def pack(self) -> bytes:
        """
        Serialize the message
        """
        return msgpack.packb((self.id.bytes, self.type.bytes, self.data))
