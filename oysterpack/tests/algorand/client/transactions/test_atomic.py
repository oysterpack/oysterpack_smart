import unittest

from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.transaction import SignedTransaction

from oysterpack.algorand.client.accounts.kmd import (
    WalletSession,
    WalletName,
    WalletPassword,
)
from oysterpack.algorand.client.accounts.kmd import WalletTransactionSigner
from oysterpack.algorand.client.transactions.payment import transfer_algo
from tests.algorand.test_support import AlgorandTestSupport


class WalletTransactionSignerTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_with_atomic_transaction_composer(self):
        account1 = self.sandbox_default_wallet.list_keys()[0]
        account2 = self.sandbox_default_wallet.list_keys()[1]
        account3 = self.sandbox_default_wallet.list_keys()[2]

        suggested_params = self.algod_client.suggested_params

        txn1 = transfer_algo(
            suggested_params=suggested_params,
            sender=account1,
            receiver=account2,
            amount=100000,
        )
        txn2 = transfer_algo(
            suggested_params=suggested_params,
            sender=account1,
            receiver=account3,
            amount=100000,
        )

        txn_signer = WalletTransactionSigner(
            WalletSession(
                kmd_client=self.kmd_client,
                name=WalletName(self.sandbox_default_wallet.name),
                password=WalletPassword(self.sandbox_default_wallet.pswd),
                get_auth_addr=self.get_auth_addr(),
            )
        )

        txn_composer = AtomicTransactionComposer()
        txn_composer.add_transaction(TransactionWithSigner(txn1, txn_signer))
        txn_composer.add_transaction(TransactionWithSigner(txn2, txn_signer))
        txn_composer.execute(self.algod_client, 4)

    def test_sign_transaction(self):
        account1 = self.sandbox_default_wallet.list_keys()[0]
        account2 = self.sandbox_default_wallet.list_keys()[1]
        account3 = self.sandbox_default_wallet.list_keys()[2]

        suggested_params = self.algod_client.suggested_params

        txn1 = transfer_algo(
            suggested_params=suggested_params,
            sender=account1,
            receiver=account2,
            amount=100000,
        )
        txn2 = transfer_algo(
            suggested_params=suggested_params,
            sender=account1,
            receiver=account3,
            amount=100000,
        )

        txn_signer = WalletTransactionSigner(
            WalletSession(
                kmd_client=self.kmd_client,
                name=WalletName(self.sandbox_default_wallet.name),
                password=WalletPassword(self.sandbox_default_wallet.pswd),
                get_auth_addr=self.get_auth_addr(),
            )
        )

        # sign all of the txns
        txns = [txn1, txn2]
        indexes = range(len(txns))
        signed_txns = txn_signer.sign_transactions(txns, indexes)
        self.assertEqual(len(signed_txns), 2)
        for signed_txn in signed_txns:
            self.assertEqual(type(signed_txn), SignedTransaction)
        for txn, signed_txn in zip(txns, signed_txns):
            self.assertEqual(txn, signed_txn.transaction)

        with self.subTest("sign a sublist of the transactions"):
            txns = [txn1, txn2]
            indexes = [1]
            signed_txns = txn_signer.sign_transactions(txns, indexes)
            self.assertEqual(len(signed_txns), 1)
            self.assertEqual(signed_txns[0].transaction, txn2)


if __name__ == "__main__":
    unittest.main()
