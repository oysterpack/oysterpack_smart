import unittest

from algosdk.transaction import Multisig
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.core.message import (
    Message,
    MessageType,
    SignedMessage,
    MultisigMessage,
)


class MessageTestCase(unittest.TestCase):
    def test_pack_unpack(self):
        msg = Message.create(MessageType(), b"data")

        packed_msg = msg.pack()
        msg_2 = Message.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


class SignedMessageDataTestCase(unittest.TestCase):
    def test_pack_unpack(self):
        algo_private_key = AlgoPrivateKey()

        msg = SignedMessage.sign(
            private_key=algo_private_key,
            msg_type=MessageType(),
            data=ULID().bytes,
        )

        self.assertTrue(msg.verify())

        packed_msg = msg.pack()
        msg_2 = SignedMessage.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


class MultisigMessageDataTestCase(unittest.TestCase):
    def test_pack_unpack(self):
        keys = [AlgoPrivateKey() for _ in range(3)]

        data = ULID().bytes

        multisig = Multisig(
            version=1, threshold=2, addresses=[key.signing_address for key in keys]
        )

        multisig.subsigs[0].signature = keys[0].sign(data).signature
        multisig.subsigs[2].signature = keys[2].sign(data).signature

        msg = MultisigMessage(
            multisig=multisig,
            msg_type=MessageType(),
            data=data,
        )

        self.assertTrue(msg.verify())

        packed_msg = msg.pack()
        msg_2 = MultisigMessage.unpack(packed_msg)

        self.assertEqual(msg, msg_2)


if __name__ == "__main__":
    unittest.main()
