import unittest
from base64 import b64decode
from typing import cast

from algosdk.account import generate_account
from algosdk.encoding import decode_address
from algosdk.transaction import wait_for_confirmation, SignedTransaction
from beaker import sandbox
from beaker.consts import algo
from nacl.exceptions import CryptoError

from algorand.test_support import get_sandbox_accounts
from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    signing_address_to_verify_key,
    encryption_address_to_public_key,
    verify_message, )
from oysterpack.algorand.client.model import Address, MicroAlgos
from oysterpack.algorand.client.transactions.payment import transfer_algo


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

        with self.subTest(
            "create AlgoPrivatekey with new auto generated Algorand account"
        ):
            algo_private_key_3 = AlgoPrivateKey()
            signed_msg = algo_private_key_3.sign(b"data")
            verify_message(
                signed_msg.message,
                signed_msg.signature,
                algo_private_key.signing_address,
            )

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
        sender = AlgoPrivateKey()
        recipient = AlgoPrivateKey()

        msg = b"Algorand is the future of finance"
        with self.subTest("recipient decrypts encrypted message from sender"):
            encrypted_msg = sender.encrypt(msg, recipient.encryption_address)
            decrypted_msg = recipient.decrypt(encrypted_msg, sender.encryption_address)
            self.assertEqual(decrypted_msg, msg)

        with self.subTest(
            "decrypting a message using the wrong recipient address should raise a CryptoError"
        ):
            wrong_recipient = AlgoPrivateKey()
            with self.assertRaises(CryptoError):
                wrong_recipient.decrypt(encrypted_msg, sender.encryption_address)

        with self.subTest(
            "decrypting a message using the wrong sender address should raise a CryptoError"
        ):
            wrong_sender = AlgoPrivateKey()
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
        signer = AlgoPrivateKey()

        msg = b"message"
        signed_msg = signer.sign(msg)

        self.assertTrue(verify_message(signed_msg.message, signed_msg.signature, signer.signing_address))

        with self.subTest(
            "verifing a message using wrong signing address should return False"
        ):
            other_signer = AlgoPrivateKey()
            self.assertFalse(
                verify_message(signed_msg.message, signed_msg.signature, other_signer.signing_address)
            )

    def test_transaction_signer(self):
        funding_account = get_sandbox_accounts().pop()
        sender = AlgoPrivateKey()
        receiver = AlgoPrivateKey()

        # fund the sender account
        algod_client = sandbox.get_algod_client()
        txn = transfer_algo(
            sender=Address(funding_account.address),
            receiver=sender.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=algod_client.suggested_params()
        )
        signed_txn = cast(SignedTransaction,funding_account.signer.sign_transactions([txn], [0])[0])
        txid = algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client,txid)

        # transfer ALGO from sender account to receiver account
        txn = transfer_algo(
            sender=sender.signing_address,
            receiver=receiver.signing_address,
            amount=MicroAlgos(int(0.1 * algo)),
            suggested_params=algod_client.suggested_params()
        )
        signed_txn = cast(SignedTransaction, sender.sign_transactions([txn], [0])[0])
        txid = algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client, txid)


if __name__ == "__main__":
    unittest.main()
