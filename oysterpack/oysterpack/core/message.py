"""
Standardized messaging format
"""
from dataclasses import dataclass

import msgpack  # type: ignore
from ulid import ULID


@dataclass(slots=True)
class Message:
    """
    Message

    :field:`id` - unique message ID
    :field:`type` - message type
    :field:`data` - msgpack serialization format
    """

    id: ULID
    type: ULID
    data: bytes

    @classmethod
    def create(cls, msg_type: ULID, data: bytes) -> "Message":
        """
        Constructor
        """
        return cls(
            id=ULID(),
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
            id=ULID.from_bytes(id),
            type=ULID.from_bytes(type),
            data=data,
        )

    def pack(self) -> bytes:
        """
        Serialize the message
        """
        return msgpack.packb((self.id.bytes, self.type.bytes, self.data))
