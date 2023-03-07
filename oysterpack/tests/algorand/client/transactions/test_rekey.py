import unittest

from algosdk.transaction import wait_for_confirmation
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
    def test_rekey_account_transaction_and_then_revoke_rekeyed_account(self):
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

        addresses: list[Address] = wallet_session.list_keys()
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


if __name__ == "__main__":
    unittest.main()
