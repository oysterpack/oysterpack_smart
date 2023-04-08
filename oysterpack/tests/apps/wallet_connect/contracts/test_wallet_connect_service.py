import unittest

import algosdk
from beaker.client import ApplicationClient
from beaker.consts import algo
from ulid import ULID

from oysterpack.algorand.beaker_utils import get_app_method
from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee
from oysterpack.apps.wallet_connect.contracts import (
    wallet_connect_service,
    wallet_connect_app,
)
from oysterpack.apps.wallet_connect.contracts.wallet_connect_service import Permission
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

        wallet_connect_service_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_service.app,
            sender=creator.address,
            signer=creator.signer,
        )

        wallet_connect_service_client.create()

        with self.subTest("when the creator opts in, he is automatically granted admin permission"):
            wallet_connect_service_client.fund(1 * algo)
            wallet_connect_service_client.opt_in(creator.address)

            result = wallet_connect_service_client.call(
                get_app_method(app_spec, "contains_permissions"),
                sender=creator.address,
                signer=creator.signer,
                account=creator.address,
                permissions=Permission.Admin.value,
            )
            self.assertTrue(result.return_value)

    def test_create_app(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        admin = accounts.pop()

        app_spec = wallet_connect_service.app.build(self.algod_client)

        wallet_connect_service_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_service.app,
            sender=creator.address,
            signer=creator.signer,
        )

        wallet_connect_service_client.create()
        wallet_connect_service_client.fund(1 * algo)
        wallet_connect_service_client.opt_in(creator.address)
        wallet_connect_service_client.call(
            get_app_method(app_spec, "grant_permissions"),
            account=creator.address,
            permissions=Permission.CreateApp.value,
        )

        result = wallet_connect_service_client.call(
            get_app_method(app_spec, "contains_permissions"),
            sender=creator.address,
            signer=creator.signer,
            account=creator.address,
            permissions=Permission.Admin.value | Permission.CreateApp.value,
        )
        self.assertTrue(result.return_value)

        name = str(ULID())
        url = "https://foo.com"
        enabled = True

        # ACT
        app_id = wallet_connect_service_client.call(
            get_app_method(app_spec, "create_app"),
            sender=creator.address,
            signer=creator.signer,
            boxes=[(0, name.encode())],
            suggested_params=suggested_params_with_flat_flee(
                self.algod_client, txn_count=2
            ),
            name=name,
            url=url,
            enabled=enabled,
            admin=admin.address,
        ).return_value

        app_id_bytes = wallet_connect_service_client.get_box_contents(name.encode())
        app_id_from_box = int.from_bytes(app_id_bytes)
        self.assertEqual(app_id, app_id_from_box)

        wallet_connect_app_client = ApplicationClient(
            self.algod_client,
            app_id=app_id,
            app=wallet_connect_app.app,
            sender=admin.address,
            signer=admin.signer,
        )

        #
        result = wallet_connect_app_client.call(
            get_app_method(app_spec, "contains_permissions"),
            sender=creator.address,
            signer=creator.signer,
            account=admin.address,
            permissions=Permission.Admin.value,
        )
        self.assertFalse(result.return_value)

    def test_create_account(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()

        app_spec = wallet_connect_service.app.build(self.algod_client)

        wallet_connect_service_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_service.app,
            sender=creator.address,
            signer=creator.signer,
        )

        wallet_connect_service_client.create()

        # grant the create permissions to create accounts
        wallet_connect_service_client.fund(1 * algo)
        wallet_connect_service_client.opt_in(creator.address)
        wallet_connect_service_client.call(
            get_app_method(app_spec, "grant_permissions"),
            account=creator.address,
            permissions=Permission.CreateAccount.value,
        )

        result = wallet_connect_service_client.call(
            get_app_method(app_spec, "contains_permissions"),
            sender=creator.address,
            signer=creator.signer,
            account=creator.address,
            permissions=Permission.Admin.value | Permission.CreateAccount.value,
        )
        self.assertTrue(result.return_value)

        user_account = AlgoPrivateKey()

        # ACT
        address_type = algosdk.abi.address_type.AddressType()
        app_id = wallet_connect_service_client.call(
            get_app_method(app_spec, "create_account"),
            sender=creator.address,
            signer=creator.signer,
            boxes=[(0, address_type.encode(user_account.signing_address))],
            suggested_params=suggested_params_with_flat_flee(
                self.algod_client, txn_count=2
            ),
            account=user_account.signing_address,
        ).return_value

        app_id_bytes = wallet_connect_service_client.get_box_contents(address_type.encode(user_account.signing_address))
        app_id_from_box = int.from_bytes(app_id_bytes)
        self.assertEqual(app_id, app_id_from_box)


if __name__ == "__main__":
    unittest.main()
