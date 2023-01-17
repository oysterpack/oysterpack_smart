import unittest

from ulid import ULID

from oysterpack.algorand.accounts.kmd import list_wallets, get_wallet, WalletName, WalletPassword, create_wallet, \
    WalletAlreadyExistsError, recover_wallet, Mnemonic
from oysterpack.algorand.accounts.test_support import KmdTestSupport


class KmdTest(KmdTestSupport, unittest.TestCase):

    def test_all_wallets(self):
        kmd_wallets = list_wallets(self._kmd_client)
        print(kmd_wallets)

    def test_lookup_wallet_exists(self):
        """
        lookup a wallet that does exist
        :return:
        """
        kmd_wallets = list_wallets(self._kmd_client)
        for wallet in kmd_wallets:
            lookup_result = get_wallet(self._kmd_client, wallet.name)
            self.assertIsNotNone(lookup_result)
            self.assertEqual(lookup_result, wallet)

    def test_lookup_wallet_not_exists(self):
        """
        Looking up a wallet that does not exist should return None
        :return:
        """
        invalid_wallet_name = str(ULID())
        result = get_wallet(self._kmd_client, WalletName(invalid_wallet_name))
        self.assertIsNone(result)

    def test_create_new_wallet(self):
        wallet_name = WalletName(str(ULID()))
        wallet_password = WalletPassword(wallet_name)
        new_wallet = create_wallet(self._kmd_client, wallet_name, wallet_password)

        self.assertEqual(new_wallet.name, wallet_name)
        self.assertEqual(new_wallet, get_wallet(self._kmd_client, new_wallet.name))

        # trying to create a wallet that already exists should raise a WalletAlreadyExistsError
        with self.subTest('wallet already exists'):
            with self.assertRaises(WalletAlreadyExistsError):
                create_wallet(self._kmd_client, wallet_name, wallet_password)

    def test_recover_wallet(self):
        wallet_recovery_mnemonic = 'film expose buzz access prepare pond jeans perfect laundry autumn believe empower clap inside bulk pistol dumb art east flip noodle myth bachelor about move'
        wallet_name = WalletName(str(ULID()))
        wallet_password = WalletPassword(wallet_name)
        recovered_wallet = recover_wallet(self._kmd_client,
                                          wallet_name,
                                          wallet_password,
                                          Mnemonic.from_word_list(wallet_recovery_mnemonic))

        self.assertEqual(recovered_wallet.name, wallet_name)
        self.assertEqual(recovered_wallet, get_wallet(self._kmd_client, recovered_wallet.name))

        # trying to recover a wallet that already exists should raise a WalletAlreadyExistsError
        with self.subTest('wallet already exists'):
            with self.assertRaises(WalletAlreadyExistsError):
                recover_wallet(self._kmd_client,
                               wallet_name,
                               wallet_password,
                               Mnemonic.from_word_list(wallet_recovery_mnemonic))

        with self.subTest('recover wallet again using a different name will create a new wallet'):
            wallet_name = WalletName(str(ULID()))  # different name
            recovered_wallet = recover_wallet(self._kmd_client,
                                              wallet_name,
                                              wallet_password,
                                              Mnemonic.from_word_list(wallet_recovery_mnemonic))

            self.assertEqual(recovered_wallet.name, wallet_name)
            self.assertEqual(recovered_wallet, get_wallet(self._kmd_client, recovered_wallet.name))


if __name__ == '__main__':
    unittest.main()
