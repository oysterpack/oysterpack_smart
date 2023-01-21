import unittest

from oysterpack.algorand.accounts import Address, get_auth_address
from oysterpack.algorand.test_support import AlgorandTestSupport
from oysterpack.algorand.transactions.rekey import rekey, rekey_back


class RekeyTestCase(AlgorandTestSupport, unittest.TestCase):
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
        txn = PaymentTxn(sender=rekey_to,
                         receiver=account,
                         amt=1000000,  # 1 ALGO
                         sp=self.algod_client.suggested_params())
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id, 4)

        # rekey
        txn = rekey(account=account,
                    rekey_to=rekey_to,
                    suggested_params=self.algod_client.suggested_params)
        signed_txn = txn.sign(private_key)
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id, 4)

        # confirm that the account has been rekeyed
        self.assertEqual(get_auth_address(address=account, algod_client=self.algod_client),
                         rekey_to)

        # revoke the rekeyed account
        txn = rekey_back(account=account, suggested_params=self.algod_client.suggested_params)
        signed_txn = txn.sign(self.sandbox_default_wallet.export_key(rekey_to))
        txn_id = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txn_id, 4)

        # confirm that the rekeyed account has been revoked
        self.assertEqual(get_auth_address(address=account, algod_client=self.algod_client),
                         account)


if __name__ == '__main__':
    unittest.main()
