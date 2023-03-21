import unittest
from dataclasses import dataclass
from typing import Self

import msgpack
from nacl.exceptions import CryptoError
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.messaging.secure_message import (
    EncryptedMessage,
    SignedEncryptedMessage, pack_secure_message, unpack_secure_message,
)
from oysterpack.core.message import Serializable, MessageType


@dataclass(slots=True)
class Data(Serializable):
    text: str

    @classmethod
    def message_type(cls) -> MessageType:
        return MessageType.from_str("01GW27XJ8KKSBYPWJEY481G4FN")

    def pack(self) -> bytes:
        """
        Packs the object into bytes
        """
        return msgpack.packb(self.text)

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        return cls(msgpack.unpackb(packed))


class SecureMessageTestCase(unittest.TestCase):
    def test_decrypt_message(self):
        # SETUP
        sender_private_key = AlgoPrivateKey()
        recipient_private_key = AlgoPrivateKey()
        data = ULID().bytes

        # encrypt
        encrypted_msg = EncryptedMessage.encrypt(
            sender_private_key=sender_private_key,
            recipient=recipient_private_key.encryption_address,
            msg=data,
        )
        # decrypt and check decrypted message mataches
        self.assertEqual(data, encrypted_msg.decrypt(recipient_private_key))

        with self.subTest("when decrypting with invalid private key"):
            other_private_key = AlgoPrivateKey()
            with self.assertRaises(CryptoError):
                encrypted_msg.decrypt(other_private_key)

        with self.subTest("when decrypting altered msg"):
            # alter message
            encrypted_msg.encrypted_msg = encrypted_msg.encrypted_msg + b"1"
            with self.assertRaises(CryptoError):
                encrypted_msg.decrypt(recipient_private_key)

    def test_secure_message(self):
        # SETUP
        sender_private_key = AlgoPrivateKey()
        recipient_private_key = AlgoPrivateKey()

        encrypted_msg = EncryptedMessage.encrypt(
            sender_private_key=sender_private_key,
            recipient=recipient_private_key.encryption_address,
            msg=ULID().bytes,
        )

        secure_message = SignedEncryptedMessage.sign(sender_private_key, encrypted_msg)
        self.assertTrue(secure_message.verify())

        with self.subTest("when decrypting with invalid private key"):
            other_private_key = AlgoPrivateKey()
            secure_message.sender = other_private_key.signing_address
            self.assertFalse(secure_message.verify())

        with self.subTest("when message has been altered"):
            secure_message.sender = sender_private_key.signing_address
            secure_message.secret_msg.encrypted_msg += b"1"
            self.assertFalse(secure_message.verify())

    def test_secure_message_packing(self):
        # SETUP
        sender_private_key = AlgoPrivateKey()
        recipient_private_key = AlgoPrivateKey()

        encrypted_msg = EncryptedMessage.encrypt(
            sender_private_key=sender_private_key,
            recipient=recipient_private_key.encryption_address,
            msg=ULID().bytes,
        )

        secure_message = SignedEncryptedMessage.sign(sender_private_key, encrypted_msg)
        self.assertTrue(secure_message.verify())

        packed_msg = secure_message.pack()
        secure_message_2 = SignedEncryptedMessage.unpack(packed_msg)
        self.assertEqual(secure_message, secure_message_2)
        self.assertTrue(secure_message_2.verify())

    def test_pack_secure_message(self):
        sender_private_key = AlgoPrivateKey()
        recipient_private_key = AlgoPrivateKey()
        data = Data("data")

        secure_message_bytes = pack_secure_message(sender_private_key, data, recipient_private_key.encryption_address)

        msg = unpack_secure_message(recipient_private_key, secure_message_bytes)
        self.assertEqual(data.message_type(), msg.msg_type)
        self.assertEqual(data, Data.unpack(msg.data))


if __name__ == "__main__":
    unittest.main()
