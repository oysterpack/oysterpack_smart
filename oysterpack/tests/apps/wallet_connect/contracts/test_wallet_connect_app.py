import unittest

from beaker.client import ApplicationClient

from oysterpack.algorand import beaker_utils
from oysterpack.algorand.beaker_utils import get_app_method
from oysterpack.apps.wallet_connect.contracts import wallet_connect_app
from oysterpack.apps.wallet_connect.contracts.wallet_connect_app import Permissions
from tests.algorand.test_support import AlgorandTestCase


class WalletConnectAppTestCase(AlgorandTestCase):
    def test_app_build(self):
        app_spec = wallet_connect_app.app.build(self.algod_client)
        app_spec.export(".")

    def test_create(self):
        # SETUP
        app_spec = wallet_connect_app.app.build()

        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        admin = accounts.pop()

        app_client = ApplicationClient(self.algod_client, app=wallet_connect_app.app)

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
        self.assertEqual(
            admin.address, beaker_utils.to_address(app_state["global_admin"])
        )

        with self.subTest(
            "when admin account is not opted in, then the account has no permissions"
        ):
            result = app_client.call(
                get_app_method(app_spec, "contains_permissions"),
                sender=creator.address,
                signer=creator.signer,
                account=admin.address,
                permissions=Permissions.Admin.value,
            )
            self.assertFalse(result.return_value)

        with self.subTest(
            "when admin account opts in, the account is granted admin permissions"
        ):
            app_client.opt_in(sender=admin.address, signer=admin.signer)

            result = app_client.call(
                get_app_method(app_spec, "contains_permissions"),
                sender=creator.address,
                signer=creator.signer,
                account=admin.address,
                permissions=Permissions.Admin.value,
            )
            self.assertTrue(result.return_value)

            admin_local_state = app_client.get_local_state(admin.address)
            self.assertEqual(
                Permissions.Admin.value, admin_local_state["account_permissions"]
            )

        with self.subTest(
            "when non-admin accounts optin, their local state is initialized with no permissions"
        ):
            app_client.opt_in(sender=creator.address, signer=creator.signer)
            creator_local_state = app_client.get_local_state(creator.address)
            self.assertEqual(
                0,
                creator_local_state["account_permissions"],
                "account should have no permissions",
            )

            result = app_client.call(
                get_app_method(app_spec, "contains_permissions"),
                sender=creator.address,
                signer=creator.signer,
                account=creator.address,
                permissions=Permissions.Admin.value,
            )
            self.assertFalse(result.return_value)

        with self.subTest("admin grants permissions to creator account"):
            permissions = Permissions.EnableApp.value | Permissions.DisableApp.value
            result = app_client.call(
                get_app_method(app_spec, "grant_permissions"),
                sender=admin.address,
                signer=admin.signer,
                account=creator.address,
                permissions=permissions,
            )
            self.assertEqual(permissions, result.return_value)
            creator_local_state = app_client.get_local_state(creator.address)
            self.assertEqual(
                permissions,
                creator_local_state["account_permissions"],
            )


if __name__ == "__main__":
    unittest.main()
