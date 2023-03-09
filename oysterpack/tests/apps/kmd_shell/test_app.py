import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from time import sleep

from beaker import sandbox
from beaker.consts import algo

from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.apps.kmd_shell.app import App
from tests.algorand.test_support import AlgorandTestCase


class AppTestCase(AlgorandTestCase):
    config = f"""
[algod]
token="{sandbox.clients.DEFAULT_ALGOD_TOKEN}"
url="{sandbox.clients.DEFAULT_ALGOD_ADDRESS}"

[kmd]
token="{sandbox.kmd.DEFAULT_KMD_TOKEN}"
url="{sandbox.kmd.DEFAULT_KMD_ADDRESS}"
"""

    def test_app(self):
        with self.subTest("init app from TOML config file"):
            with NamedTemporaryFile() as f:
                f.write(self.config.encode())
                f.flush()
                config_file_path = Path(gettempdir()) / f.name
                app = App.from_config_file(config_file_path)

                # check config
                self.assertIn("algod", app.config)
                self.assertIn("kmd", app.config)
                self.assertEqual(
                    sandbox.clients.DEFAULT_ALGOD_ADDRESS, app.config["algod"]["url"]
                )
                self.assertEqual(
                    sandbox.kmd.DEFAULT_KMD_ADDRESS, app.config["kmd"]["url"]
                )

                self.assertGreater(len(app.list_wallets()), 0)
                self.assertIsNone(app.connected_wallet)

        with self.subTest("rekeying"):
            app.connect_wallet(
                sandbox.kmd.DEFAULT_KMD_WALLET_NAME,
                sandbox.kmd.DEFAULT_KMD_WALLET_PASSWORD,
            )
            self.assertIsNotNone(app.connected_wallet)

            accounts = app.list_wallet_accounts()
            account_1 = accounts.pop()
            account_2 = accounts.pop()

            self.assertEqual(0, len(app.get_rekeyed_accounts()))

            self.assertEqual(account_1, app.get_auth_address(account_1))
            txid = app.rekey(account_1, account_2)
            self.assertEqual(account_2, app.get_auth_address(account_1))
            pending_transaction_info = self.algod_client.pending_transaction_info(txid)
            self.assertEqual("pay", pending_transaction_info["txn"]["txn"]["type"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["snd"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["rcv"])
            self.assertEqual(account_2, pending_transaction_info["txn"]["txn"]["rekey"])

            rekeyed_accounts = app.get_rekeyed_accounts()
            self.assertEqual(1, len(rekeyed_accounts))
            self.assertEqual(rekeyed_accounts[account_1], account_2)

            txid = app.rekey_back(account_1)
            pending_transaction_info = self.algod_client.pending_transaction_info(txid)
            self.assertEqual("pay", pending_transaction_info["txn"]["txn"]["type"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["snd"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["rcv"])
            self.assertEqual(account_1, pending_transaction_info["txn"]["txn"]["rekey"])

            self.assertEqual(account_1, app.get_auth_address(account_1))
            self.assertEqual(0, len(app.get_rekeyed_accounts()))

        with self.subTest("transfer algo between 2 accounts in the same wallet"):
            app.connect_wallet(
                sandbox.kmd.DEFAULT_KMD_WALLET_NAME,
                sandbox.kmd.DEFAULT_KMD_WALLET_PASSWORD,
            )

            # retrieve accounts that have ALGO balance >= 1 ALGO
            accounts = app.list_wallet_accounts()

            sender = accounts.pop()
            sender_algo_balance = app.algod_client.account_info(sender)["amount"]
            while sender_algo_balance < 1 * algo:
                sender = accounts.pop()
                sender_algo_balance = app.algod_client.account_info(sender)["amount"]

            receiver = accounts.pop()
            receiver_algo_balance = app.algod_client.account_info(receiver)["amount"]
            while receiver_algo_balance < 1 * algo:
                receiver = accounts.pop()
                receiver_algo_balance = app.algod_client.account_info(receiver)[
                    "amount"
                ]

            txid = app.transfer_algo(
                sandbox.kmd.DEFAULT_KMD_WALLET_NAME,
                sandbox.kmd.DEFAULT_KMD_WALLET_PASSWORD,
                sender,
                receiver,
                MicroAlgos(100_000),
            )

            self.assertEqual(
                receiver_algo_balance + 100_000,
                app.algod_client.account_info(receiver)["amount"],
            )

            sleep(0.1)  # give time to index
            txn = self.indexer.transaction(txid)
            self.assertEqual(sender, txn["transaction"]["sender"])
            self.assertEqual(
                receiver, txn["transaction"]["payment-transaction"]["receiver"]
            )

        with self.subTest("transfer algo from rekeyed account"):
            sender_auth_account = accounts.pop()
            app.rekey(sender, sender_auth_account)

            receiver_algo_balance = app.algod_client.account_info(receiver)["amount"]
            txid = app.transfer_algo(
                sandbox.kmd.DEFAULT_KMD_WALLET_NAME,
                sandbox.kmd.DEFAULT_KMD_WALLET_PASSWORD,
                sender,
                receiver,
                MicroAlgos(100_000),
            )
            self.assertEqual(
                receiver_algo_balance + 100_000,
                app.algod_client.account_info(receiver)["amount"],
            )

            sleep(0.1)  # give time to index
            txn = self.indexer.transaction(txid)
            self.assertEqual(sender, txn["transaction"]["sender"])
            self.assertEqual(
                receiver, txn["transaction"]["payment-transaction"]["receiver"]
            )

            app.rekey_back(sender)


if __name__ == "__main__":
    unittest.main()
