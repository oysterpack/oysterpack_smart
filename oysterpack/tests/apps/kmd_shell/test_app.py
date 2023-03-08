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
        print(self.config)
        with NamedTemporaryFile() as f:
            f.write(self.config.encode())
            config_file_path = Path(gettempdir()) / f.name
            print(config_file_path)
            App.from_config_file(config_file_path)


if __name__ == "__main__":
    unittest.main()
