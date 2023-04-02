import unittest

from beaker.client import ApplicationClient

from oysterpack.algorand import beaker_utils
from oysterpack.apps.wallet_connect.contracts import wallet_connect_app
from oysterpack.apps.wallet_connect.contracts.wallet_connect_app import Permissions
from tests.algorand.test_support import AlgorandTestCase


class WalletConnectAppTestCase(AlgorandTestCase):
    def test_create(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        admin = accounts.pop()

        app_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_app.app
        )

        name = "Foo"
        url = "https://foo.com"
        enabled = True

        # ACT
        app_client.create(
            sender=creator.address,
            signer=creator.signer,
            name=name,
            url=url,
            enabled=enabled,
            admin=admin.address,
        )

        # ASSERT
        app_state = app_client.get_global_state()
        self.assertEqual(name, app_state["name"])
        self.assertEqual(url, app_state["url"])
        self.assertTrue(app_state["enabled"])
        self.assertEqual(admin.address, beaker_utils.to_address(app_state["global_admin"]))

        app_client.opt_in(sender=admin.address, signer=admin.signer)
        admin_local_state = app_client.get_local_state(admin.address)
        self.assertEqual(Permissions.Admin.value, admin_local_state["account_permissions"])

        app_client.opt_in(sender=creator.address, signer=creator.signer)
        creator_local_state = app_client.get_local_state(creator.address)
        self.assertEqual(0, creator_local_state["account_permissions"], "account should have no permissions")


if __name__ == '__main__':
    unittest.main()
