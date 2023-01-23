import unittest

from algosdk.account import generate_account
from algosdk.transaction import wait_for_confirmation

from oysterpack.algorand.transactions.account import close_account
from oysterpack.algorand.transactions.payment import transfer_algo
from tests.algorand.test_support import AlgorandTestSupport


class CloseAccountTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_close_account(self):
        account = self.sandbox_default_wallet.list_keys()[0]
        private_key, account2 = generate_account()

        # fund account2
        txn = transfer_algo(sender=account, receiver=account2, amount=1000000,
                            suggested_params=self.algod_client.suggested_params)
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client=self.algod_client, txid=txid)

        account2_info = self.algod_client.account_info(account2)
        self.assertEqual(account2_info['amount'], 1000000)

        # close account
        txn = close_account(account=account2, close_to=account, suggested_params=self.algod_client.suggested_params)
        signed_txn = txn.sign(private_key)
        txid = self.algod_client.send_transaction(signed_txn)
        tx_info = wait_for_confirmation(algod_client=self.algod_client, txid=txid)
        # check that the account was closed to the specified account
        self.assertEqual(tx_info['txn']['txn']['close'], account)
        self.assertEqual(tx_info['txn']['txn']['rcv'], account)
        # check that the closed account has a zero ALGO balance
        account2_info = self.algod_client.account_info(account2)
        self.assertEqual(account2_info['amount'], 0)


if __name__ == '__main__':
    unittest.main()
