import unittest

from oysterpack.algorand.accounts.account import Mnemonic


class AccountTestCase(unittest.TestCase):

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


if __name__ == '__main__':
    unittest.main()
