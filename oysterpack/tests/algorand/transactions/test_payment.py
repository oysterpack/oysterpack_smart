import unittest

import algosdk

from tests.algorand.test_support import AlgorandTestSupport
from oysterpack.algorand.transactions.payment import transfer_algo, MicroAlgos


class PaymentTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_algo_transfer_transaction(self):
        sender = self.sandbox_default_wallet.list_keys()[0]
        _private_key, receiver = algosdk.account.generate_account()

        # create a payment txn with no note
        amount = MicroAlgos(1000000)
        txn = transfer_algo(sender=sender, receiver=receiver, amount=amount,
                                        suggested_params=self.algod_client.suggested_params)
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        algosdk.transaction.wait_for_confirmation(algod_client=self.algod_client, txid=txid, wait_rounds=4)

        receiver_account_info = self.algod_client.account_info(receiver)
        self.assertEqual(receiver_account_info['amount'], amount)

        with self.subTest('sending the same transaction again should fail because of transaction lease'):
            with self.assertRaises(algosdk.error.AlgodHTTPError) as err:
                txid = self.algod_client.send_transaction(signed_txn)
                algosdk.transaction.wait_for_confirmation(algod_client=self.algod_client, txid=txid,
                                                          wait_rounds=4)
            self.assertTrue('TransactionPool.Remember' in str(err.exception))

        # create a payment txn with a note
        amount = MicroAlgos(1000000)
        note = 'transaction note'
        txn = transfer_algo(sender=sender, receiver=receiver, amount=amount, note=note,
                                        suggested_params=self.algod_client.suggested_params)
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        tx_info = algosdk.transaction.wait_for_confirmation(algod_client=self.algod_client, txid=txid,
                                                            wait_rounds=4)
        self.assertEqual(algosdk.encoding.base64.b64decode(tx_info['txn']['txn']['note']).decode(), note)

        with self.subTest(
                'sending the same transaction with note attached again should fail because of transaction lease'
        ):
            with self.assertRaises(algosdk.error.AlgodHTTPError) as err:
                txid = self.algod_client.send_transaction(signed_txn)
                algosdk.transaction.wait_for_confirmation(algod_client=self.algod_client, txid=txid,
                                                          wait_rounds=4)
            self.assertTrue('TransactionPool.Remember' in str(err.exception))


if __name__ == '__main__':
    unittest.main()
