import unittest

from beaker.client import ApplicationClient
from beaker.consts import algo
from ulid import ULID

from oysterpack.algorand.beaker_utils import get_app_method
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee
from oysterpack.apps.wallet_connect.contracts import wallet_connect_service
from oysterpack.apps.wallet_connect.contracts.wallet_connect_service import Permissions
from tests.algorand.test_support import AlgorandTestCase


class WalletConnectAppTestCase(AlgorandTestCase):
    def test_app_build(self):
        app_spec = wallet_connect_service.app.build(self.algod_client)
        app_spec.export(".")

    def test_create(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        admin = accounts.pop()

        app_spec = wallet_connect_service.app.build(self.algod_client)

        app_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_service.app,
            sender=creator.address,
            signer=creator.signer,
        )

        app_client.create()
        app_client.fund(1 * algo)
        app_client.opt_in(creator.address)
        app_client.call(
            get_app_method(app_spec, "grant_permissions"),
            account=creator.address,
            permissions=Permissions.CreateApp.value,
        )

        result = app_client.call(
            get_app_method(app_spec, "contains_permissions"),
            sender=creator.address,
            signer=creator.signer,
            account=creator.address,
            permissions=Permissions.Admin.value | Permissions.CreateApp.value,
        )
        self.assertTrue(result.return_value)

        name = str(ULID())
        url = "https://foo.com"
        enabled = True

        # ACT
        app_id = app_client.call(
            get_app_method(app_spec, "create_app"),
            sender=creator.address,
            signer=creator.signer,
            boxes=[(0, name.encode())],
            suggested_params=suggested_params_with_flat_flee(self.algod_client,txn_count=2),
            name=name,
            url=url,
            enabled=enabled,
            admin=admin.address,
        ).return_value

        # ASSERT
        # app_state = app_client.get_global_state()
        # self.assertEqual(name, app_state["name"])
        # self.assertEqual(url, app_state["url"])
        # self.assertTrue(app_state["enabled"])
        # self.assertEqual(admin.address, beaker_utils.to_address(app_state["global_admin"]))
        #
        # app_client.opt_in(sender=admin.address, signer=admin.signer)
        # admin_local_state = app_client.get_local_state(admin.address)
        # self.assertEqual(Permissions.Admin.value, admin_local_state["account_permissions"])
        #
        # app_client.opt_in(sender=creator.address, signer=creator.signer)
        # creator_local_state = app_client.get_local_state(creator.address)
        # self.assertEqual(0, creator_local_state["account_permissions"], "account should have no permissions")
        #

        #
        # result = app_client.call(
        #     get_app_method(app_spec, "contains_permissions"),
        #     sender=creator.address,
        #     signer=creator.signer,
        #     account=creator.address,
        #     permissions=Permissions.Admin.value,
        # )
        # self.assertFalse(result.return_value)


if __name__ == '__main__':
    unittest.main()
