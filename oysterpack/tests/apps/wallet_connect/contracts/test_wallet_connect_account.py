import pprint
import unittest

from beaker.client import ApplicationClient

from oysterpack.algorand import beaker_utils
from oysterpack.apps.wallet_connect.contracts import wallet_connect_account
from tests.algorand.test_support import AlgorandTestCase


class WalletConnectAppTestCase(AlgorandTestCase):

    def test_app_build(self):
        app_spec = wallet_connect_account.application.build(self.algod_client)
        app_spec.export(".")

    def test_create(self):
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        user_account = accounts.pop()

        app_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_account.application,
            sender=creator.address,
            signer=creator.signer,
        )

        app_client.create(account=user_account.address)
        app_state = app_client.get_global_state()
        pprint.pp(app_state)
        self.assertEqual(user_account.address, beaker_utils.to_address(app_state["account"]))
        self.assertEqual(0, app_state["expiration"])

    def test_connect_app(self):
        pass

if __name__ == "__main__":
    unittest.main()