import unittest
from dataclasses import field, dataclass
from typing import Self, ClassVar

import msgpack  # type: ignore
from algosdk.transaction import Multisig
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.core.message import (
    Message,
    MessageType,
    SignedMessage,
    MultisigMessage,
    Serializable,
)


class MessageTestCase(unittest.TestCase):
    def test_pack_unpack(self):
        msg = Message.create(MessageType(), b"data")

        packed_msg = msg.pack()
        msg_2 = Message.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


@dataclass(slots=True)
class FooMsg(Serializable):
    MSG_TYPE: ClassVar[MessageType] = MessageType()

    data: ULID = field(default_factory=ULID)

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    def pack(self) -> bytes:
        """
        Packs the object into bytes
        """
        return msgpack.packb(self.data.bytes)

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        return cls(ULID.from_bytes(msgpack.unpackb(packed)))


class SignedMessageDataTestCase(unittest.TestCase):
    def test_pack_unpack(self):
        algo_private_key = AlgoPrivateKey()

        msg = SignedMessage.sign(private_key=algo_private_key, msg=FooMsg())

        self.assertTrue(msg.verify())

        packed_msg = msg.pack()
        msg_2 = SignedMessage.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


class MultisigMessageDataTestCase(unittest.TestCase):
    def test_pack_unpack(self):
        keys = [AlgoPrivateKey() for _ in range(3)]

        data = ULID().bytes

        multisig = Multisig(
            version=1,
            threshold=2,
            addresses=[key.signing_address for key in keys],
        )

        msg = MultisigMessage(
            multisig=multisig,
            msg_type=MessageType(),
            data=data,
        )

        msg.sign(keys[0])
        msg.sign(keys[2])

        self.assertTrue(msg.verify())

        packed_msg = msg.pack()
        msg_2 = MultisigMessage.unpack(packed_msg)

        self.assertEqual(msg, msg_2)


if __name__ == "__main__":
    unittest.main()
