import pprint
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir

from beaker import sandbox

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
                self.assertEqual(sandbox.clients.DEFAULT_ALGOD_ADDRESS, app.config["algod"]["url"])
                self.assertEqual(sandbox.kmd.DEFAULT_KMD_ADDRESS, app.config["kmd"]["url"])

                self.assertGreater(len(app.list_wallets()), 0)
                self.assertIsNone(app.connected_wallet)

        with self.subTest("rekeying"):
            app.connect_wallet(sandbox.kmd.DEFAULT_KMD_WALLET_NAME, sandbox.kmd.DEFAULT_KMD_WALLET_PASSWORD)
            self.assertIsNotNone(app.connected_wallet)

            pprint.pp(("rekeyed_accounts",app.get_rekeyed_accounts()))

            accounts = app.list_wallet_accounts()
            account_1 = accounts.pop()
            account_2 = accounts.pop()

            self.assertEqual(0, len(app.get_rekeyed_accounts()))

            self.assertEqual(account_1, app.get_auth_address(account_1))
            app.rekey(account_1, account_2)
            self.assertEqual(account_2, app.get_auth_address(account_1))

            rekeyed_accounts = app.get_rekeyed_accounts()
            self.assertEqual(1, len(rekeyed_accounts))
            self.assertEqual(rekeyed_accounts[account_1], account_2)

            app.rekey_back(account_1)
            self.assertEqual(account_1, app.get_auth_address(account_1))
            self.assertEqual(0, len(app.get_rekeyed_accounts()))



if __name__ == "__main__":
    unittest.main()
