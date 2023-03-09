import pprint
import unittest

from algosdk import mnemonic
from algosdk.account import generate_account
from algosdk.error import InvalidThresholdError
from algosdk.transaction import wait_for_confirmation, Multisig, MultisigTransaction
from algosdk.wallet import Wallet
from beaker import sandbox
from beaker.consts import algo
from ulid import ULID

from oysterpack.algorand.client.accounts import (
    get_auth_address_callable,
    get_auth_address,
)
from oysterpack.algorand.client.accounts.error import (
    InvalidWalletPasswordError,
    WalletAlreadyExistsError,
    WalletDoesNotExistError,
    KmdUrlError,
    InvalidKmdTokenError,
    DuplicateWalletNameError,
)
from oysterpack.algorand.client.accounts.kmd import (
    list_wallets,
    get_wallet,
    WalletName,
    WalletPassword,
    create_wallet,
    recover_wallet,
    WalletSession,
    create_kmd_client,
)
from oysterpack.algorand.client.model import Mnemonic, Address, MicroAlgos
from oysterpack.algorand.client.transactions import payment
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.algorand.client.transactions.rekey import rekey
from tests.algorand.test_support import AlgorandTestCase


class AlgorandTest(AlgorandTestCase):
    def test_create_kmd_client(self):
        # create a wallet using valid connection params
        kmd_client = create_kmd_client(
            url=self.kmd_client.kmd_address, token=self.kmd_client.kmd_token
        )

        # assert that the KMD address and token were set properly
        self.assertEqual(kmd_client.kmd_address, self.kmd_client.kmd_address)
        self.assertEqual(kmd_client.kmd_token, self.kmd_client.kmd_token)
        # check that the client can successfully submit requests to the KMD server
        kmd_client.list_wallets()

        with self.subTest("create client with invalid URL"):
            with self.assertRaises(KmdUrlError):
                create_kmd_client(url="BADURL", token=self.kmd_client.kmd_token)

            with self.assertRaises(KmdUrlError):
                create_kmd_client(
                    url="http://localhost", token=self.kmd_client.kmd_token
                )

            with self.assertRaises(KmdUrlError):
                create_kmd_client(
                    url="http://localhost:4001", token=self.kmd_client.kmd_token
                )

            with self.assertRaises(KmdUrlError):
                create_kmd_client(url="", token=self.kmd_client.kmd_token)

        with self.subTest("create client with invalid token"):
            with self.assertRaises(InvalidKmdTokenError):
                create_kmd_client(
                    url=self.kmd_client.kmd_address, token="INVALID_TOKEN"
                )

            with self.assertRaises(InvalidKmdTokenError):
                create_kmd_client(url=self.kmd_client.kmd_address, token="")

    def test_all_wallets(self):
        kmd_wallets = list_wallets(self.kmd_client)
        self.assertTrue(len(kmd_wallets) > 0)

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
        with self.subTest("wallet already exists"):
            with self.assertRaises(WalletAlreadyExistsError):
                create_wallet(self.kmd_client, wallet_name, wallet_password)

    def test_recover_wallet(self):
        wallet_recovery_mnemonic = "film expose buzz access prepare pond jeans perfect laundry autumn believe empower clap inside bulk pistol dumb art east flip noodle myth bachelor about move"
        wallet_name = WalletName(str(ULID()))
        wallet_password = WalletPassword(wallet_name)
        recovered_wallet = recover_wallet(
            self.kmd_client,
            wallet_name,
            wallet_password,
            Mnemonic.from_word_list(wallet_recovery_mnemonic),
        )

        self.assertEqual(recovered_wallet.name, wallet_name)
        self.assertEqual(
            recovered_wallet, get_wallet(self.kmd_client, recovered_wallet.name)
        )

        # trying to recover a wallet using a name that already exists should raise a WalletAlreadyExistsError
        with self.subTest("wallet already exists"):
            with self.assertRaises(WalletAlreadyExistsError):
                recover_wallet(
                    self.kmd_client,
                    wallet_name,
                    wallet_password,
                    Mnemonic.from_word_list(wallet_recovery_mnemonic),
                )

        with self.subTest(
            "recover wallet again using a different name will create a new wallet"
        ):
            wallet_name = WalletName(str(ULID()))  # different name
            recovered_wallet = recover_wallet(
                self.kmd_client,
                wallet_name,
                wallet_password,
                Mnemonic.from_word_list(wallet_recovery_mnemonic),
            )

            self.assertEqual(recovered_wallet.name, wallet_name)
            self.assertEqual(
                recovered_wallet, get_wallet(self.kmd_client, recovered_wallet.name)
            )


class WalletSessionTests(AlgorandTestCase):
    def _create_test_wallet_session(
        self, wallet: Wallet | None = None
    ) -> WalletSession:
        if wallet is None:
            wallet = super().create_test_wallet()
        return WalletSession(
            kmd_client=wallet.kcl,
            name=WalletName(wallet.name),
            password=WalletPassword(wallet.pswd),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

    def test_create_wallet_session(self):
        _wallet = super().create_test_wallet()
        session = self._create_test_wallet_session(_wallet)

        # check that the wallet session that was created was for the specified wallet name
        # The master derivation key is unique per wallet. Thus, check the master derivation key against the key looked
        # up directly via the KMD client
        session_mdc_mnemonic = session.export_master_derivation_key()
        wallet_mdc = self.kmd_client.export_master_derivation_key(
            handle=_wallet.handle, password=_wallet.pswd
        )
        self.assertEqual(
            session_mdc_mnemonic,
            Mnemonic.from_word_list(mnemonic.from_master_derivation_key(wallet_mdc)),
        )

        with self.subTest("with invalid name"):
            with self.assertRaises(WalletDoesNotExistError):
                WalletSession(
                    kmd_client=_wallet.kcl,
                    name=WalletName(str(ULID())),
                    password=WalletPassword(_wallet.pswd),
                    get_auth_addr=get_auth_address_callable(self.algod_client),
                )

        with self.subTest("with invalid password"):
            with self.assertRaises(InvalidWalletPasswordError):
                WalletSession(
                    kmd_client=_wallet.kcl,
                    name=WalletName(_wallet.name),
                    password=WalletPassword(str(ULID())),
                    get_auth_addr=get_auth_address_callable(self.algod_client),
                )

        with self.subTest("KmdClient raises exception"):
            with self.assertRaises(KmdUrlError):
                WalletSession(
                    kmd_client=create_kmd_client(url="http://badurl", token=""),
                    name=WalletName(_wallet.name),
                    password=WalletPassword(_wallet.pswd),
                    get_auth_addr=get_auth_address_callable(self.algod_client),
                )

    def test__del__(self):
        session = self._create_test_wallet_session()

        # when the object finalizer is run, the session handle is released
        session.__del__()
        # it should be ok to try to release the hancle again
        session.__del__()

    def test_rename(self):
        # setup
        _wallet = super().create_test_wallet()
        session = self._create_test_wallet_session(_wallet)

        # rename the wallet using a unique name
        new_name = str(ULID())
        session.rename(new_name=WalletName(new_name))
        self.assertEqual(session.name, new_name)

        # check that a new wallet session with the new name can be created
        session = WalletSession(
            kmd_client=_wallet.kcl,
            name=WalletName(new_name),
            password=WalletPassword(_wallet.pswd),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )
        session.list_keys()

        with self.subTest("using the name of another existing wallet should fail"):
            _wallet2 = super().create_test_wallet()
            with self.assertRaises(DuplicateWalletNameError):
                session.rename(_wallet2.name)

        with self.subTest("blank name should fail"):
            with self.assertRaises(ValueError):
                session.rename(" ")

        with self.subTest("using the same name should fail"):
            with self.assertRaises(ValueError) as err:
                session.rename(session.name)
            self.assertEqual(
                str(err.exception),
                "new wallet name cannot be the same as the current wallet name",
            )

    def test_generate_key(self):
        session = self._create_test_wallet_session()
        self.assertEqual(len(session.list_keys()), 0)

        for i in range(1, 6):
            address = session.generate_key()
            self.assertEqual(len(session.list_keys()), i)
            self.assertTrue(address in session.list_keys())
            self.assertTrue(session.contains_key(address))

    def test_delete_key(self):
        session = self._create_test_wallet_session()
        self.assertEqual(len(session.list_keys()), 0)
        address = session.generate_key()
        self.assertTrue(session.contains_key(address))
        session.delete_key(address)
        self.assertFalse(session.contains_key(address))

    def test_export_key(self):
        session = self._create_test_wallet_session()
        address = session.generate_key()

        account_mnemonic = session.export_key(address)
        self.assertIsNotNone(account_mnemonic)

        # import the key into another wallet and verify it maps to the same public address
        _wallet2 = super().create_test_wallet()
        address2 = _wallet2.import_key(mnemonic.to_private_key(str(account_mnemonic)))
        self.assertEqual(address, address2)

    def test_sign_transaction(self):
        import algosdk
        from oysterpack.algorand.client.accounts.error import KeyNotFoundError

        session = self._create_test_wallet_session()

        from algosdk.transaction import PaymentTxn

        for address in session.list_keys():
            txn = PaymentTxn(
                sender=address,
                receiver=address,
                amt=0,
                sp=self.algod_client.suggested_params(),
            )
            session.sign_transaction(txn)

        with self.subTest("when signing account does not exist in the wallet"):
            _, address = algosdk.account.generate_account()
            txn = PaymentTxn(
                sender=address,
                receiver=address,
                amt=0,
                sp=self.algod_client.suggested_params(),
            )
            with self.assertRaises(KeyNotFoundError):
                session.sign_transaction(txn)

    def test_sign_transaction_using_rekeyed_account(self):
        """
        Test Steps
        ----------
        1. generate a new account
        2. use the first account in the sandbox default wallet as the rekey_to account
        3. fund the new account with ALGO using the rekey_to account
        4. rekey the account
        5. sign a new payment transaction for the rekeyed account using a WalletSession for the sandbox default wallet.
           This checks that the WalletSession can sign transactions for rekeyed accounts.
        """
        import algosdk
        from algosdk.transaction import PaymentTxn, wait_for_confirmation
        from oysterpack.algorand.client.accounts.error import KeyNotFoundError

        sandbox_default_wallet = self.sandbox_default_wallet
        sandbox_default_wallet_session = WalletSession(
            kmd_client=sandbox_default_wallet.kcl,
            name=WalletName(sandbox_default_wallet.name),
            password=WalletPassword(sandbox_default_wallet.pswd),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        # generate an account and rekey it to the first account in the sandbox default wallet
        private_key, account = algosdk.account.generate_account()
        rekey_to = sandbox_default_wallet.list_keys()[0]

        # fund the account
        txn = payment.transfer_algo(
            sender=rekey_to,
            receiver=account,
            amount=1000000,
            suggested_params=self.algod_client.suggested_params(),
        )

        signed_txn = sandbox_default_wallet.sign_transaction(txn)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)

        # rekey the account
        txn = rekey(
            account=Address(account),
            rekey_to=rekey_to,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)

        # send payment from account, but sign the transaction with the authorized account
        # this checks that the WalletSession can sign transactions for rekeyed accounts
        txn = PaymentTxn(
            sender=account,
            receiver=account,
            amt=0,
            sp=self.algod_client.suggested_params(),
        )
        sandbox_default_wallet_session.sign_transaction(txn)

        with self.subTest("when signing account does not exist in the wallet"):
            _, address = algosdk.account.generate_account()
            txn = PaymentTxn(
                sender=address,
                receiver=address,
                amt=0,
                sp=self.algod_client.suggested_params(),
            )
            session = self._create_test_wallet_session()
            with self.assertRaises(KeyNotFoundError):
                session.sign_transaction(txn)

    def test_rekeying(self):
        sandbox_default_wallet = self.sandbox_default_wallet
        sandbox_default_wallet_session = WalletSession(
            kmd_client=sandbox_default_wallet.kcl,
            name=WalletName(sandbox_default_wallet.name),
            password=WalletPassword(sandbox_default_wallet.pswd),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        accounts = sandbox.get_accounts()
        account_1 = Address(accounts.pop().address)
        account_2 = Address(accounts.pop().address)
        account_3 = Address(accounts.pop().address)

        with self.subTest("rekey the account"):
            txid = sandbox_default_wallet_session.rekey(
                account_1, account_2, self.algod_client
            )
            pending_transaction_info = self.algod_client.pending_transaction_info(txid)
            self.assertEqual("pay", pending_transaction_info["txn"]["txn"]["type"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["snd"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["rcv"])
            self.assertEqual(account_2, pending_transaction_info["txn"]["txn"]["rekey"])

            # confirm that the account has been rekeyed
            self.assertEqual(
                get_auth_address(address=account_1, algod_client=self.algod_client),
                account_2,
            )

        with self.subTest("rotate the auth account by rekeying again"):
            txid = sandbox_default_wallet_session.rekey(
                account_1, account_3, self.algod_client
            )
            pending_transaction_info = self.algod_client.pending_transaction_info(txid)
            self.assertEqual("pay", pending_transaction_info["txn"]["txn"]["type"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["snd"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["rcv"])
            self.assertEqual(account_3, pending_transaction_info["txn"]["txn"]["rekey"])

            # confirm that the account has been rekeyed
            self.assertEqual(
                get_auth_address(address=account_1, algod_client=self.algod_client),
                account_3,
            )

        with self.subTest("rekey back"):
            txid = sandbox_default_wallet_session.rekey_back(
                account_1, self.algod_client
            )
            pending_transaction_info = self.algod_client.pending_transaction_info(txid)
            self.assertEqual("pay", pending_transaction_info["txn"]["txn"]["type"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["snd"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["rcv"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["rekey"])

            # confirm that the account has been rekeyed
            self.assertEqual(
                get_auth_address(address=account_1, algod_client=self.algod_client),
                account_1,
            )

        with self.subTest(
            "when trying to rekey an account to an account that does not exist in the same wallet"
        ):
            _private_key, address = generate_account()
            with self.assertRaises(AssertionError):
                sandbox_default_wallet_session.rekey(
                    account_1, Address(address), self.algod_client
                )

            with self.assertRaises(AssertionError):
                _private_key, address = generate_account()
                sandbox_default_wallet_session.rekey(
                    Address(address), account_2, self.algod_client
                )

        with self.subTest("rekeying to an account that is rekeyed should work"):
            # rekey account_1 -> account_2
            sandbox_default_wallet_session.rekey(
                account_1, account_2, self.algod_client
            )
            # rekey account_2 -> account_1
            sandbox_default_wallet_session.rekey(
                account_2, account_1, self.algod_client
            )

            self.assertEqual(
                get_auth_address(address=account_1, algod_client=self.algod_client),
                account_2,
            )
            self.assertEqual(
                get_auth_address(address=account_2, algod_client=self.algod_client),
                account_1,
            )

            # send a payment from account_1 -> account_3
            # txn should be signed by account_2
            txn = payment.transfer_algo(
                sender=account_1,
                receiver=account_3,
                amount=MicroAlgos(1 * algo),
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = sandbox_default_wallet_session.sign_transaction(txn)
            txid = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txid)
            txn = self.algod_client.pending_transaction_info(txid)
            self.assertEqual(account_2, txn["txn"]["sgnr"])

            # rekey back each account
            for account in [account_1, account_2]:
                sandbox_default_wallet_session.rekey_back(account, self.algod_client)

            for account in [account_1, account_2]:
                self.assertEqual(account, get_auth_address(account, self.algod_client))

    def test_multisig(self):
        sandbox_default_wallet = self.sandbox_default_wallet
        sandbox_default_wallet_session = WalletSession(
            kmd_client=sandbox_default_wallet.kcl,
            name=WalletName(sandbox_default_wallet.name),
            password=WalletPassword(sandbox_default_wallet.pswd),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        accounts = sandbox.get_accounts()
        account_1 = Address(accounts.pop().address)
        account_2 = Address(accounts.pop().address)
        account_3 = Address(accounts.pop().address)

        with self.subTest("import multisig"):
            multisig_1 = Multisig(
                version=1,
                threshold=2,
                addresses=[
                    account_1,
                    account_2,
                    account_3,
                ],
            )

            multisig_1_address = sandbox_default_wallet_session.import_multisig(
                multisig_1
            )
            multisigs = sandbox_default_wallet_session.list_multisigs()
            pprint.pp(multisigs)
            self.assertIn(multisig_1_address, multisigs)
            self.assertTrue(
                sandbox_default_wallet_session.contains_multisig(multisig_1.address())
            )
            self.assertEqual(
                multisig_1,
                sandbox_default_wallet_session.export_multisig(multisig_1.address()),
            )

        with self.subTest("delete multisig"):
            deleted = sandbox_default_wallet_session.delete_multisig(
                multisig_1.address()
            )
            self.assertTrue(deleted)
            self.assertFalse(
                sandbox_default_wallet_session.contains_multisig(multisig_1.address())
            )
            self.assertIsNone(
                sandbox_default_wallet_session.export_multisig(multisig_1.address())
            )

        with self.subTest("import invalid multisig"):
            multisig_1 = Multisig(
                version=1,
                threshold=4,
                addresses=[
                    account_1,
                    account_2,
                    account_3,
                ],
            )

            with self.assertRaises(InvalidThresholdError):
                sandbox_default_wallet_session.import_multisig(multisig_1)

    def test_multisig_txn_signing(self):
        sandbox_default_wallet = self.sandbox_default_wallet
        sandbox_default_wallet_session = WalletSession(
            kmd_client=sandbox_default_wallet.kcl,
            name=WalletName(sandbox_default_wallet.name),
            password=WalletPassword(sandbox_default_wallet.pswd),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        accounts = sandbox.get_accounts()
        account_1 = Address(accounts.pop().address)
        account_2 = Address(accounts.pop().address)
        account_3 = Address(accounts.pop().address)

        multisig_1 = Multisig(
            version=1,
            threshold=2,
            addresses=[
                account_1,
                account_2,
                account_3,
            ],
        )

        sandbox_default_wallet_session.import_multisig(multisig_1)

        # fund multisig account
        txn = transfer_algo(
            sender=account_1,
            receiver=multisig_1.address(),
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = sandbox_default_wallet_session.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # transfer ALGO from multisig_1 to account_1
        txn = transfer_algo(
            sender=multisig_1.address(),
            receiver=account_1,
            amount=MicroAlgos(100_000),
            suggested_params=self.algod_client.suggested_params(),
        )

        multisig_1_starting_balance = self.algod_client.account_info(
            multisig_1.address()
        )["amount"]

        signed_txn = sandbox_default_wallet_session.sign_multisig_transaction(
            MultisigTransaction(txn, multisig_1)
        )
        self.assertEqual(3, len(signed_txn.multisig.subsigs))
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        multisig_1_ending_balance = self.algod_client.account_info(
            multisig_1.address()
        )["amount"]
        self.assertEqual(
            101_000,
            multisig_1_starting_balance - multisig_1_ending_balance,
            "difference should be 0.1 ALGO + 0.001 ALGO txn fee",
        )

    def test_multisig_txn_signing_with_rekeyed_account(self):
        """
        Rekeying has no effect on signing multisig txns.

        The multisig txn can only be signed using the accounts that are defined by the multisig.
        """

        sandbox_default_wallet = self.sandbox_default_wallet
        sandbox_default_wallet_session = WalletSession(
            kmd_client=sandbox_default_wallet.kcl,
            name=WalletName(sandbox_default_wallet.name),
            password=WalletPassword(sandbox_default_wallet.pswd),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        accounts = sandbox.get_accounts()
        account_1 = Address(accounts.pop().address)
        account_2 = Address(accounts.pop().address)
        account_3 = Address(accounts.pop().address)

        account_4 = sandbox_default_wallet_session.generate_key()

        txn = transfer_algo(
            sender=account_1,
            receiver=account_4,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = sandbox_default_wallet_session.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        sandbox_default_wallet_session.rekey(account_4, account_3, self.algod_client)
        self.assertEqual(account_3, get_auth_address(account_4, self.algod_client))

        multisig_1 = Multisig(
            version=1,
            threshold=3,
            addresses=[
                account_1,
                account_2,
                account_4,  # rekeyed to account_3
            ],
        )

        sandbox_default_wallet_session.import_multisig(multisig_1)

        # fund multisig account
        txn = transfer_algo(
            sender=account_1,
            receiver=multisig_1.address(),
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = sandbox_default_wallet_session.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # transfer ALGO from multisig_1 to account_1
        txn = transfer_algo(
            sender=multisig_1.address(),
            receiver=account_1,
            amount=MicroAlgos(100_000),
            suggested_params=self.algod_client.suggested_params(),
        )

        multisig_1_starting_balance = self.algod_client.account_info(
            multisig_1.address()
        )["amount"]

        signed_txn = sandbox_default_wallet_session.sign_multisig_transaction(
            MultisigTransaction(txn, multisig_1)
        )
        pprint.pp(signed_txn.dictify())
        self.assertEqual(3, len(signed_txn.multisig.subsigs))
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        multisig_1_ending_balance = self.algod_client.account_info(
            multisig_1.address()
        )["amount"]
        self.assertEqual(
            101_000,
            multisig_1_starting_balance - multisig_1_ending_balance,
            "difference should be 0.1 ALGO + 0.001 ALGO txn fee",
        )


if __name__ == "__main__":
    unittest.main()
