import json
import unittest

from algosdk.account import generate_account
from algosdk.transaction import wait_for_confirmation, Multisig, MultisigTransaction
from beaker import sandbox
from beaker.consts import algo

from oysterpack.algorand.client.accounts import (
    Address,
    get_auth_address,
    get_auth_address_callable,
)
from oysterpack.algorand.client.accounts.kmd import WalletSession
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.algorand.client.transactions.rekey import rekey, rekey_back
from tests.algorand.test_support import AlgorandTestCase


class RekeyTestCase(AlgorandTestCase):
    def test_rekey_account_transaction_and_then_rekey_back(self):
        """
        Test Steps
        ----------
        1. generate new account
        2. fund account with ALGO using first account in the sandbox default wallet
        3. rekey the account to the first account in the sandbox default wallet
        4. confirm that the account has been rekeyed
        5. revoke the rekeyed account
        6. confirm that the account's authorized account has been reset to itself
        :return:
        """

        import algosdk
        from algosdk.transaction import wait_for_confirmation, PaymentTxn

        private_key, account = algosdk.account.generate_account()
        account = Address(account)
        # rekey the account using the first account in the sandbox default wallet
        rekey_to = self.sandbox_default_wallet.list_keys()[0]

        # fund the account
        txn = PaymentTxn(
            sender=rekey_to,
            receiver=account,
            amt=1000000,  # 1 ALGO
            sp=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)

        # rekey
        txn = rekey(
            account=account,
            rekey_to=rekey_to,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)

        # confirm that the account has been rekeyed
        self.assertEqual(
            get_auth_address(address=account, algod_client=self.algod_client), rekey_to
        )

        # revoke the rekeyed account
        txn = rekey_back(
            account=account,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(self.sandbox_default_wallet.export_key(rekey_to))
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)

        # confirm that the rekeyed account has been revoked
        self.assertEqual(
            get_auth_address(address=account, algod_client=self.algod_client), account
        )

    def test_rekey_using_kmd_accounts(self) -> None:
        wallet_session = WalletSession(
            kmd_client=sandbox.kmd.get_client(),
            name=sandbox.kmd.DEFAULT_KMD_WALLET_NAME,
            password=sandbox.kmd.DEFAULT_KMD_WALLET_PASSWORD,
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        addresses: list[Address] = wallet_session.list_accounts()
        account_1 = addresses.pop()
        account_2 = addresses.pop()

        with self.subTest("rekey account_1 -> account_2"):
            txn = rekey(
                account=account_1,
                rekey_to=account_2,
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = wallet_session.sign_transaction(txn)
            txn_id = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txn_id)

            # confirm that the account has been rekeyed
            self.assertEqual(
                get_auth_address(address=account_1, algod_client=self.algod_client),
                account_2,
            )

            # transfer ALGO from account_1 to account_2
            # the transaction should be signed by account_2
            txn = transfer_algo(
                sender=account_1,
                receiver=account_2,
                amount=MicroAlgos(1 * algo),
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = wallet_session.sign_transaction(txn)
            txn_id = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txn_id)

        with self.subTest("rekey back account_2 -> account_1"):
            txn = rekey_back(
                account=account_1,
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = wallet_session.sign_transaction(txn)
            txn_id = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txn_id)

            # confirm that the account has been rekeyed
            self.assertEqual(
                get_auth_address(address=account_1, algod_client=self.algod_client),
                account_1,
            )

            # transfer ALGO from account_1 to account_2
            # the transaction should be signed by account_1
            txn = transfer_algo(
                sender=account_1,
                receiver=account_2,
                amount=MicroAlgos(1 * algo),
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = wallet_session.sign_transaction(txn)
            txn_id = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txn_id)

    def test_rekey_multisig_with_simple_key(self):
        # SETUP
        # create multsig
        accounts = {
            address: private_key
            for private_key, address in (generate_account() for i in range(3))
        }
        multisig = Multisig(
            version=1, threshold=len(accounts), addresses=accounts.keys()
        )

        # fund multisig
        funder = self.get_sandbox_accounts().pop()
        txn = transfer_algo(
            sender=funder.address,
            receiver=multisig.address(),
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(funder.private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)
        multisig_account_info = self.algod_client.account_info(multisig.address())
        print(json.dumps(multisig_account_info, indent=3))

        multisig_auth_account_private_key, multisig_auth_account = generate_account()

        txn = rekey(
            account=multisig.address(),
            rekey_to=multisig_auth_account,
            suggested_params=self.algod_client.suggested_params(),
        )
        multisig_txn = MultisigTransaction(txn, multisig)
        for private_key in accounts.values():
            multisig_txn.sign(private_key)
        txn_id = self.algod_client.send_transaction(multisig_txn)
        wait_for_confirmation(self.algod_client, txn_id)

        # confirm that the account has been rekeyed
        multisig_account_info = self.algod_client.account_info(multisig.address())
        print("after rekeying:", json.dumps(multisig_account_info, indent=3))
        self.assertEqual(
            get_auth_address(
                address=multisig.address(), algod_client=self.algod_client
            ),
            multisig_auth_account,
        )

        txn = transfer_algo(
            sender=multisig.address(),
            receiver=funder.address,
            amount=MicroAlgos(10000),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(multisig_auth_account_private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)

    def test_rekey_multisig_with_underlying_keys_rekeyed(self):
        # SETUP
        # create multsig
        accounts = [generate_account() for i in range(3)]
        multisig = Multisig(
            version=1,
            threshold=len(accounts),
            addresses=[account for (_private_key, account) in accounts],
        )

        # fund multisig
        funder = self.get_sandbox_accounts().pop()
        txn = transfer_algo(
            sender=funder.address,
            receiver=multisig.address(),
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(funder.private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)
        multisig_account_info = self.algod_client.account_info(multisig.address())
        print(json.dumps(multisig_account_info, indent=3))

        # fund underlying accounts
        for (_private_key, account) in accounts:
            funder = self.get_sandbox_accounts().pop()
            txn = transfer_algo(
                sender=funder.address,
                receiver=account,
                amount=MicroAlgos(1 * algo),
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = txn.sign(funder.private_key)
            txn_id = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txn_id)

        # rekey the underlying accounts
        auth_accounts = [generate_account() for i in range(3)]

        for (private_key, account), (_auth_private_key, auth_account) in zip(
            accounts, auth_accounts
        ):
            txn = rekey(
                account=account,
                rekey_to=auth_account,
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = txn.sign(private_key)
            txn_id = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txn_id)

        for (private_key, account), (_auth_private_key, auth_account) in zip(
            accounts, auth_accounts
        ):
            self.assertEqual(
                get_auth_address(address=account, algod_client=self.algod_client),
                auth_account,
            )

        # transfer funds from multisig
        txn = transfer_algo(
            sender=multisig.address(),
            receiver=funder.address,
            amount=MicroAlgos(10000),
            suggested_params=self.algod_client.suggested_params(),
        )
        multisig_txn = MultisigTransaction(txn, multisig)
        for (private_key, _account) in accounts:
            multisig_txn.sign(private_key)
        txn_id = self.algod_client.send_transaction(multisig_txn)
        wait_for_confirmation(self.algod_client, txn_id)

    def test_rekey_multisig_with_multisig(self):
        # SETUP
        # create multsig
        accounts = [generate_account() for i in range(3)]
        multisig = Multisig(
            version=1,
            threshold=len(accounts),
            addresses=[account for (_private_key, account) in accounts],
        )

        # fund multisig
        funder = self.get_sandbox_accounts().pop()
        txn = transfer_algo(
            sender=funder.address,
            receiver=multisig.address(),
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(funder.private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)
        multisig_account_info = self.algod_client.account_info(multisig.address())
        print(json.dumps(multisig_account_info, indent=3))

        # create second multisig, which will be using for rekeying
        auth_accounts = [generate_account() for i in range(3)]
        auth_multisig = Multisig(
            version=1,
            threshold=len(accounts),
            addresses=[account for (_private_key, account) in auth_accounts],
        )

        # fund multisig
        funder = self.get_sandbox_accounts().pop()
        txn = transfer_algo(
            sender=funder.address,
            receiver=auth_multisig.address(),
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = txn.sign(funder.private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id)
        multisig_account_info = self.algod_client.account_info(auth_multisig.address())
        print(json.dumps(multisig_account_info, indent=3))

        # rekey multisig to auth_multisig
        txn = rekey(
            account=multisig.address(),
            rekey_to=auth_multisig.address(),
            suggested_params=self.algod_client.suggested_params(),
        )
        multisig_txn = MultisigTransaction(txn, multisig)
        for (private_key, _account) in accounts:
            multisig_txn.sign(private_key)
        txn_id = self.algod_client.send_transaction(multisig_txn)
        wait_for_confirmation(self.algod_client, txn_id)
        multisig_account_info = self.algod_client.account_info(auth_multisig.address())
        print(json.dumps(multisig_account_info, indent=3))

        # transfer funds from multisig
        txn = transfer_algo(
            sender=multisig.address(),
            receiver=funder.address,
            amount=MicroAlgos(10000),
            suggested_params=self.algod_client.suggested_params(),
        )
        multisig_txn = MultisigTransaction(txn, auth_multisig)
        for (private_key, _account) in auth_accounts:
            multisig_txn.sign(private_key)
        txn_id = self.algod_client.send_transaction(multisig_txn)
        wait_for_confirmation(self.algod_client, txn_id)


if __name__ == "__main__":
    unittest.main()
