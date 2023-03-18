import unittest

from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.core.message import Message, MessageType, SignedMessageData


class MessageTestCase(unittest.TestCase):
    def test_pack(self):
        msg = Message.create(MessageType(), b"data")

        packed_msg = msg.pack()
        msg_2 = Message.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


class SignedMessageDataTestCase(unittest.TestCase):
    def test_pack(self):
        algo_private_key = AlgoPrivateKey()

        msg = SignedMessageData.sign(
            private_key=algo_private_key,
            msg_type=MessageType(),
            data=ULID().bytes,
        )

        self.assertTrue(msg.verify())

        packed_msg = msg.pack()
        msg_2 = SignedMessageData.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


if __name__ == "__main__":
    unittest.main()
