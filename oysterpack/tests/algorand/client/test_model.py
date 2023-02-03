import unittest
from typing import Iterable

from algosdk import mnemonic
from algosdk.account import generate_account
from beaker.application import Application

from tests.algorand.test_support import sandbox_application_client
from oysterpack.algorand.client.model import AppID, Mnemonic
from tests.algorand.test_support import AlgorandTestSupport


class AccountModelTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_valid_mnemonic(self):
        def word_list() -> Iterable[str]:
            return map(str, range(25))

        mnemonic = Mnemonic(tuple(word_list()))
        self.assertEqual(str(mnemonic), " ".join(word_list()))

        mnemonic = Mnemonic.from_word_list(" ".join(word_list()))
        self.assertEqual(str(mnemonic), " ".join(word_list()))

    def test_invalid_mnemonic(self):
        def word_list() -> Iterable[str]:
            return map(str, range(24))

        with self.assertRaises(ValueError):
            Mnemonic(tuple(word_list()))

        with self.assertRaises(ValueError):
            Mnemonic.from_word_list(" ".join(word_list()))

    def test_to_master_derivation_key(self):
        test_wallet = self.create_test_wallet()
        mdc = test_wallet.export_master_derivation_key()
        test_wallet_mnemonic = Mnemonic.from_word_list(
            mnemonic.from_master_derivation_key(mdc)
        )
        self.assertEqual(test_wallet_mnemonic.to_master_derivation_key(), mdc)

    def test_to_private_key(self):
        sk, _pk = generate_account()
        sk_mnemonic = Mnemonic.from_word_list(mnemonic.from_private_key(sk))
        self.assertEqual(sk_mnemonic.to_private_key(), sk)


class Foo(Application):
    pass


class AppIdTestCase(unittest.TestCase):
    def test_to_address(self):
        app_client = sandbox_application_client(Foo())

        app_id, app_addess, _tx_id = app_client.create()
        app_id = AppID(app_id)
        self.assertEqual(app_id.to_address(), app_addess)


if __name__ == "__main__":
    unittest.main()
