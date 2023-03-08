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


if __name__ == "__main__":
    unittest.main()
