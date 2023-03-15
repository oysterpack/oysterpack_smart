import unittest

from algosdk.account import generate_account
from nacl.exceptions import CryptoError
from nacl.utils import EncryptedMessage
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.messaging.secure_message import (
    SecretMessage,
    SecureMessage,
)


class SecureMessageTestCase(unittest.TestCase):
    def test_decrypt_message(self):
        # SETUP
        sender_private_key = AlgoPrivateKey(generate_account()[0])
        recipient_private_key = AlgoPrivateKey(generate_account()[0])
        data = ULID().bytes

        # encrypt
        encrypted_msg = SecretMessage.encrypt(
            sender_private_key=sender_private_key,
            recipient=recipient_private_key.encryption_address,
            msg=data,
        )
        # decrypt and check decrypted message mataches
        self.assertEqual(data, encrypted_msg.decrypt(recipient_private_key))

        with self.subTest("when decrypting with invalid private key"):
            other_private_key = AlgoPrivateKey(generate_account()[0])
            with self.assertRaises(CryptoError):
                encrypted_msg.decrypt(other_private_key)

        with self.subTest("when decrypting altered msg"):
            # alter message
            encrypted_msg.encrypted_msg = EncryptedMessage._from_parts(
                combined=encrypted_msg.encrypted_msg.nonce
                + encrypted_msg.encrypted_msg.ciphertext
                + b"1",
                nonce=encrypted_msg.encrypted_msg.nonce,
                ciphertext=encrypted_msg.encrypted_msg.ciphertext + b"1",
            )
            with self.assertRaises(CryptoError):
                encrypted_msg.decrypt(recipient_private_key)

    def test_secure_message(self):
        # SETUP
        sender_private_key = AlgoPrivateKey(generate_account()[0])
        recipient_private_key = AlgoPrivateKey(generate_account()[0])

        encrypted_msg = SecretMessage.encrypt(
            sender_private_key=sender_private_key,
            recipient=recipient_private_key.encryption_address,
            msg=ULID().bytes,
        )

        secure_message = SecureMessage.sign(sender_private_key, encrypted_msg)
        self.assertTrue(secure_message.verify())

        with self.subTest("when decrypting with invalid private key"):
            other_private_key = AlgoPrivateKey(generate_account()[0])
            secure_message.sender = other_private_key.signing_address
            self.assertFalse(secure_message.verify())

        with self.subTest("when message has been altered"):
            secure_message.sender = sender_private_key.signing_address
            secure_message.secret_msg.encrypted_msg += b"1"
            self.assertFalse(secure_message.verify())

    def test_secure_message_packing(self):
        # SETUP
        sender_private_key = AlgoPrivateKey(generate_account()[0])
        recipient_private_key = AlgoPrivateKey(generate_account()[0])

        encrypted_msg = SecretMessage.encrypt(
            sender_private_key=sender_private_key,
            recipient=recipient_private_key.encryption_address,
            msg=ULID().bytes,
        )

        secure_message = SecureMessage.sign(sender_private_key, encrypted_msg)
        self.assertTrue(secure_message.verify())

        packed_msg = secure_message.pack()
        secure_message_2 = SecureMessage.unpack(packed_msg)
        self.assertEqual(secure_message, secure_message_2)
        self.assertTrue(secure_message_2.verify())


if __name__ == "__main__":
    unittest.main()
