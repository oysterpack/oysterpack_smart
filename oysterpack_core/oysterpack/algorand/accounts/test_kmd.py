import unittest

from algosdk import mnemonic
from ulid import ULID

from oysterpack.algorand.accounts.error import InvalidWalletPasswordError, WalletAlreadyExistsError, \
    WalletDoesNotExistError, KmdUrlError, InvalidKmdTokenError, DuplicateWalletNameError
from oysterpack.algorand.accounts.kmd import list_wallets, get_wallet, WalletName, WalletPassword, create_wallet, \
    recover_wallet, WalletSession, create_kmd_client
from oysterpack.algorand.accounts.model import Mnemonic
from oysterpack.algorand.accounts.test_support import KmdTestSupport


class KmdTest(KmdTestSupport, unittest.TestCase):

    def test_create_kmd_client(self):
        # create a wallet using valid connection params
        kmd_client = create_kmd_client(url=self.kmd_client.kmd_address, token=self.kmd_client.kmd_token)

        # assert that the KMD address and token were set properly
        self.assertEqual(kmd_client.kmd_address, self.kmd_client.kmd_address)
        self.assertEqual(kmd_client.kmd_token, self.kmd_client.kmd_token)
        # check that the client can successfully submit requests to the KMD server
        kmd_client.list_wallets()

        with self.subTest('create client with invalid URL'):
            with self.assertRaises(KmdUrlError):
                create_kmd_client(url='BADURL', token=self.kmd_client.kmd_token)

            with self.assertRaises(KmdUrlError):
                create_kmd_client(url='http://localhost', token=self.kmd_client.kmd_token)

            with self.assertRaises(KmdUrlError):
                create_kmd_client(url='http://localhost:4001', token=self.kmd_client.kmd_token)

            with self.assertRaises(KmdUrlError):
                create_kmd_client(url='', token=self.kmd_client.kmd_token)

        with self.subTest('create client with invalid token'):
            with self.assertRaises(InvalidKmdTokenError):
                create_kmd_client(url=self.kmd_client.kmd_address, token='INVALID_TOKEN')

            with self.assertRaises(InvalidKmdTokenError):
                create_kmd_client(url=self.kmd_client.kmd_address, token='')

    def test_all_wallets(self):
        kmd_wallets = list_wallets(self.kmd_client)
        print(kmd_wallets)

    def test_lookup_wallet_exists(self):
        """
        lookup a wallet that does exist
        :return:
        """
        kmd_wallets = list_wallets(self.kmd_client)
        for wallet in kmd_wallets:
            lookup_result = get_wallet(self.kmd_client, wallet.name)
            self.assertIsNotNone(lookup_result)
            self.assertEqual(lookup_result, wallet)

    def test_lookup_wallet_not_exists(self):
        """
        Looking up a wallet that does not exist should return None
        :return:
        """
        invalid_wallet_name = str(ULID())
        result = get_wallet(self.kmd_client, WalletName(invalid_wallet_name))
        self.assertIsNone(result)

    def test_create_new_wallet(self):
        wallet_name = WalletName(str(ULID()))
        wallet_password = WalletPassword(wallet_name)
        new_wallet = create_wallet(self.kmd_client, wallet_name, wallet_password)

        self.assertEqual(new_wallet.name, wallet_name)
        self.assertEqual(new_wallet, get_wallet(self.kmd_client, new_wallet.name))

        # trying to create a wallet that already exists should raise a WalletAlreadyExistsError
        with self.subTest('wallet already exists'):
            with self.assertRaises(WalletAlreadyExistsError):
                create_wallet(self.kmd_client, wallet_name, wallet_password)

    def test_recover_wallet(self):
        wallet_recovery_mnemonic = 'film expose buzz access prepare pond jeans perfect laundry autumn believe empower clap inside bulk pistol dumb art east flip noodle myth bachelor about move'
        wallet_name = WalletName(str(ULID()))
        wallet_password = WalletPassword(wallet_name)
        recovered_wallet = recover_wallet(self.kmd_client,
                                          wallet_name,
                                          wallet_password,
                                          Mnemonic.from_word_list(wallet_recovery_mnemonic))

        self.assertEqual(recovered_wallet.name, wallet_name)
        self.assertEqual(recovered_wallet, get_wallet(self.kmd_client, recovered_wallet.name))

        # trying to recover a wallet using a name that already exists should raise a WalletAlreadyExistsError
        with self.subTest('wallet already exists'):
            with self.assertRaises(WalletAlreadyExistsError):
                recover_wallet(self.kmd_client,
                               wallet_name,
                               wallet_password,
                               Mnemonic.from_word_list(wallet_recovery_mnemonic))

        with self.subTest('recover wallet again using a different name will create a new wallet'):
            wallet_name = WalletName(str(ULID()))  # different name
            recovered_wallet = recover_wallet(self.kmd_client,
                                              wallet_name,
                                              wallet_password,
                                              Mnemonic.from_word_list(wallet_recovery_mnemonic))

            self.assertEqual(recovered_wallet.name, wallet_name)
            self.assertEqual(recovered_wallet, get_wallet(self.kmd_client, recovered_wallet.name))


class WalletSessionTests(KmdTestSupport, unittest.TestCase):

    def test_create_wallet_session(self):
        _wallet = super().create_test_wallet()
        session = WalletSession(kmd_client=_wallet.kcl,
                                name=WalletName(_wallet.name),
                                password=WalletPassword(_wallet.pswd))

        # check that the wallet session that was created was for the specified wallet name
        # The master derivation key is unique per wallet. Thus, check the master derivation key against the key looked
        # up directly via the KMD client
        session_mdc_mnemonic = session.export_master_derivation_key()
        wallet_mdc = self.kmd_client.export_master_derivation_key(handle=_wallet.handle, password=_wallet.pswd)
        self.assertEqual(session_mdc_mnemonic, Mnemonic.from_word_list(mnemonic.from_master_derivation_key(wallet_mdc)))

        with self.subTest('with invalid name'):
            with self.assertRaises(WalletDoesNotExistError):
                WalletSession(kmd_client=_wallet.kcl,
                              name=WalletName(str(ULID())),
                              password=WalletPassword(_wallet.pswd))

        with self.subTest('with invalid password'):
            with self.assertRaises(InvalidWalletPasswordError):
                WalletSession(kmd_client=_wallet.kcl,
                              name=WalletName(_wallet.name),
                              password=WalletPassword(str(ULID())))

        with self.subTest('KmdClient raises exception'):
            with self.assertRaises(KmdUrlError):
                WalletSession(kmd_client=create_kmd_client(url='http://badurl', token=''),
                              name=WalletName(_wallet.name),
                              password=WalletPassword(_wallet.pswd))

    def test__del__(self):
        _wallet = super().create_test_wallet()
        session = WalletSession(kmd_client=_wallet.kcl,
                                name=WalletName(_wallet.name),
                                password=WalletPassword(_wallet.pswd))

        # when the object finalizer is run, the session handle is released
        session.__del__()
        # it should be ok to try to release the hancle again
        session.__del__()

    def test_rename(self):
        # setup
        _wallet = super().create_test_wallet()
        session = WalletSession(kmd_client=_wallet.kcl,
                                name=WalletName(_wallet.name),
                                password=WalletPassword(_wallet.pswd))

        # rename the wallet using a unique name
        new_name = str(ULID())
        session.rename(new_name=WalletName(new_name))
        self.assertEqual(session.name, new_name)

        # check that a new wallet session with the new name can be created
        session = WalletSession(kmd_client=_wallet.kcl,
                                name=WalletName(new_name),
                                password=WalletPassword(_wallet.pswd))
        session.list_keys()

        with self.subTest('using the name of another existing wallet should fail'):
            _wallet2 = super().create_test_wallet()
            with self.assertRaises(DuplicateWalletNameError):
                session.rename(_wallet2.name)

        with self.subTest('blank name should fail'):
            with self.assertRaises(ValueError):
                session.rename(' ')

        with self.subTest('using the same name should fail'):
            with self.assertRaises(ValueError) as err:
                session.rename(session.name)
            self.assertEqual(str(err.exception), 'new wallet name cannot be the same as the current wallet name')


if __name__ == '__main__':
    unittest.main()
