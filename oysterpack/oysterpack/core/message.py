"""
Standardized messaging format
"""
from collections import namedtuple
from dataclasses import dataclass

import msgpack  # type: ignore
from ulid import ULID

MessageTuple = namedtuple("MessageTuple", ("id", "type", "data"))


@dataclass(slots=True)
class Message:
    """
    Message
    """

    id: ULID
    type: ULID
    data: bytes

    def to_tuple(self) -> MessageTuple:
        return MessageTuple(str(self.id), str(self.type), self.data)

    @classmethod
    def from_tuple(cls, msg: MessageTuple) -> "Message":
        return cls(
            id=ULID.from_str(msg.id),
            type=ULID.from_str(msg.type),
            data=msg.data,
        )

    @classmethod
    def create(cls, type: ULID, data: bytes) -> "Message":
        return cls(
            id=ULID(),
            type=type,
            data=data,
        )

    @classmethod
    def unpack(cls, packed: bytes) -> "Message":
        (id, type, data) = msgpack.unpackb(packed, use_list=False)
        return cls(
            id=ULID.from_bytes(id),
            type=ULID.from_bytes(type),
            data=data,
        )

    def pack(self) -> bytes:
        return msgpack.packb((self.id.bytes, self.type.bytes, self.data))
