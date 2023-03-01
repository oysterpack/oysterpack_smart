import unittest
from base64 import b64decode

from algosdk.account import generate_account
from algosdk.encoding import decode_address
from nacl.exceptions import CryptoError

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    signing_address_to_verify_key,
    encryption_address_to_public_key,
    verify_message,
)


class AlgoPrivateKeyTestCase(unittest.TestCase):
    def test_initializer(self):
        sk, pk = generate_account()
        algo_private_key = AlgoPrivateKey(sk)

        with self.subTest(
            "create AlgoPrivateKey from Algorand account private key bytes"
        ):
            algo_private_key_2 = AlgoPrivateKey(b64decode(sk))
            self.assertEqual(algo_private_key.public_key, algo_private_key_2.public_key)

        with self.subTest(
            "create AlgoPrivateKey from Algorand account private key mnemonic"
        ):
            algo_private_key_2 = AlgoPrivateKey(algo_private_key.mnemonic)
            self.assertEqual(algo_private_key.public_key, algo_private_key_2.public_key)

        with self.subTest("create AlgoPrivateKey from an unsupported type"):
            with self.assertRaises(ValueError):
                AlgoPrivateKey(123)

        # check that the addresses are encoded as Algorand addreses
        decode_address(algo_private_key.signing_address)
        decode_address(algo_private_key.encryption_address)

        self.assertEqual(
            algo_private_key.signing_address,
            pk,
            "signing address should be the Algorand address",
        )
        self.assertNotEqual(
            algo_private_key.signing_address,
            algo_private_key.encryption_address,
            "the signing and encryption address should be different",
        )

        self.assertEqual(
            signing_address_to_verify_key(algo_private_key.signing_address),
            algo_private_key.signing_key.verify_key,
            "signing address conversion to a signing verification key failed",
        )
        self.assertEqual(
            encryption_address_to_public_key(algo_private_key.encryption_address),
            algo_private_key.public_key,
            "encryption address to public key conversion failed",
        )

    def test_encrypt_decrypt(self):
        sk, pk = generate_account()
        sender = AlgoPrivateKey(sk)

        sk, pk = generate_account()
        recipient = AlgoPrivateKey(sk)

        msg = b"Algorand is the future of finance"
        with self.subTest("recipient decrypts encrypted message from sender"):
            encrypted_msg = sender.encrypt(msg, recipient.encryption_address)
            decrypted_msg = recipient.decrypt(encrypted_msg, sender.encryption_address)
            self.assertEqual(decrypted_msg, msg)

        with self.subTest(
            "decrypting a message using the wrong recipient address should raise a CryptoError"
        ):
            sk, _pk = generate_account()
            wrong_recipient = AlgoPrivateKey(sk)
            with self.assertRaises(CryptoError):
                wrong_recipient.decrypt(encrypted_msg, sender.encryption_address)

        with self.subTest(
            "decrypting a message using the wrong sender address should raise a CryptoError"
        ):
            sk, _pk = generate_account()
            wrong_sender = AlgoPrivateKey(sk)
            with self.assertRaises(CryptoError):
                recipient.decrypt(encrypted_msg, wrong_sender.encryption_address)

        with self.subTest("sender is also recpient"):
            encrypted_msg = sender.encrypt(msg)
            decrypted_msg = sender.decrypt(encrypted_msg)
            self.assertEqual(decrypted_msg, msg)

            # no other account should be able to decrypt the message
            with self.assertRaises(CryptoError):
                recipient.decrypt(encrypted_msg)

    def test_sign_verify(self):
        sk, pk = generate_account()
        signer = AlgoPrivateKey(sk)

        msg = b"message"
        signed_msg = signer.sign(msg)

        self.assertTrue(verify_message(signed_msg.message, signed_msg.signature, pk))

        with self.subTest(
            "verifing a message using wrong signing address should return False"
        ):
            _sk, pk = generate_account()
            self.assertFalse(
                verify_message(signed_msg.message, signed_msg.signature, pk)
            )


if __name__ == "__main__":
    unittest.main()
