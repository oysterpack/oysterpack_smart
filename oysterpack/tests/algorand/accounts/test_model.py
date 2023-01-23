import unittest

from algosdk import mnemonic, account

from oysterpack.algorand.model import Mnemonic
from tests.algorand.test_support import AlgorandTestSupport


class AccountModelTestCase(AlgorandTestSupport, unittest.TestCase):

    def test_valid_mnemonic(self):
        word_list = lambda: map(str, range(25))
        mnemonic = Mnemonic(tuple(word_list()))
        self.assertEqual(str(mnemonic), ' '.join(word_list()))

        mnemonic = Mnemonic.from_word_list(' '.join(word_list()))
        self.assertEqual(str(mnemonic), ' '.join(word_list()))

    def test_invalid_mnemonic(self):
        word_list = lambda: map(str, range(24))
        with self.assertRaises(ValueError):
            Mnemonic(tuple(word_list()))

        with self.assertRaises(ValueError):
            Mnemonic.from_word_list(' '.join(word_list()))

    def test_to_master_derivation_key(self):
        test_wallet = self.create_test_wallet()
        mdc = test_wallet.export_master_derivation_key()
        test_wallet_mnemonic = Mnemonic.from_word_list(mnemonic.from_master_derivation_key(mdc))
        self.assertEqual(test_wallet_mnemonic.to_master_derivation_key(), mdc)

    def test_to_private_key(self):
        sk, pk = account.generate_account()
        print(sk, pk)
        sk_mnemonic = Mnemonic.from_word_list(mnemonic.from_private_key(sk))
        self.assertEqual(sk_mnemonic.to_private_key(), sk)


if __name__ == '__main__':
    unittest.main()
