import unittest
from concurrent.futures.thread import ThreadPoolExecutor
from unittest import IsolatedAsyncioTestCase

import algosdk.abi
from algosdk.encoding import decode_address
from beaker.client import ApplicationClient
from beaker.consts import algo
from ulid import ULID

from oysterpack.algorand.beaker_utils import get_app_method
from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import AppId
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee
from oysterpack.apps.wallet_connect.contracts import (
    wallet_connect_service,
    wallet_connect_app,
)
from oysterpack.apps.wallet_connect.contracts.wallet_connect_app import (
    Permission as WalletConnectAppPermission,
)
from oysterpack.apps.wallet_connect.contracts.wallet_connect_service import (
    Permission as WalletConnectServicePermissions,
)
from oysterpack.apps.wallet_connect.services.wallet_connect_service import (
    OysterPackWalletConnectService,
)
from oysterpack.core.ulid import HashableULID
from tests.algorand.test_support import AlgorandTestCase


class WalletConnectServiceTestCase(AlgorandTestCase, IsolatedAsyncioTestCase):
    executor = ThreadPoolExecutor()

    def setUp(self) -> None:
        accounts = self.get_sandbox_accounts()
        self.wallet_connect_service_creator = accounts.pop()
        self.wallet_connect_app_admin = accounts.pop()

        app_spec = wallet_connect_service.app.build(self.algod_client)

        self.wallet_connect_service_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_service.app,
            sender=self.wallet_connect_service_creator.address,
            signer=self.wallet_connect_service_creator.signer,
        )

        (
            self.wallet_connect_service_app_id,
            _app_address,
            _txid,
        ) = self.wallet_connect_service_client.create()
        self.wallet_connect_service_client.fund(1 * algo)
        self.wallet_connect_service_client.opt_in(
            self.wallet_connect_service_creator.address
        )
        self.wallet_connect_service_client.call(
            get_app_method(app_spec, "grant_permissions"),
            account=self.wallet_connect_service_creator.address,
            permissions=WalletConnectServicePermissions.CreateApp.value,
        )

        # create WalletConnectApp
        name = str(ULID())
        url = f"https://{name}.com"
        enabled = True
        self.wallet_connect_app_id = self.wallet_connect_service_client.call(
            get_app_method(app_spec, "create_app"),
            sender=self.wallet_connect_service_creator.address,
            signer=self.wallet_connect_service_creator.signer,
            boxes=[(0, name.encode())],
            suggested_params=suggested_params_with_flat_flee(
                self.algod_client,
                txn_count=2,
            ),
            name=name,
            url=url,
            enabled=enabled,
            admin=self.wallet_connect_app_admin.address,
        ).return_value

        # grant admin permissions
        self.wallet_connect_app_admin_client = ApplicationClient(
            self.algod_client,
            app_id=self.wallet_connect_app_id,
            app=wallet_connect_app.app,
            sender=self.wallet_connect_app_admin.address,
            signer=self.wallet_connect_app_admin.signer,
        )

        # optin an account into the app
        self.wallet_connect_app_admin_client.opt_in(
            sender=self.wallet_connect_service_creator.address,
            signer=self.wallet_connect_service_creator.signer,
        )
        # when the admin opts in, admin permissions are automatically granted
        self.wallet_connect_app_admin_client.opt_in(
            sender=self.wallet_connect_app_admin.address,
            signer=self.wallet_connect_app_admin.signer,
        )
        self.wallet_connect_app_admin_client.fund(1 * algo)

        # grant admin permissions to register keys to himself
        self.wallet_connect_app_admin_client.call(
            get_app_method(app_spec, "grant_permissions"),
            sender=self.wallet_connect_app_admin.address,
            signer=self.wallet_connect_app_admin.signer,
            account=self.wallet_connect_app_admin.address,
            permissions=WalletConnectAppPermission.RegisterKeys.value,
        )

        self.wallet_connect_service_client.call(
            get_app_method(app_spec, "grant_permissions"),
            sender=self.wallet_connect_service_creator.address,
            signer=self.wallet_connect_service_creator.signer,
            account=self.wallet_connect_service_creator.address,
            permissions=WalletConnectServicePermissions.CreateAccount.value,
        )

        self.user_account = AlgoPrivateKey()
        address_type = algosdk.abi.AddressType()
        self.user_account_app_id = self.wallet_connect_service_client.call(
            wallet_connect_service.create_account.method_signature(),
            suggested_params=suggested_params_with_flat_flee(
                self.algod_client, txn_count=2
            ),
            account=self.user_account.signing_address,
            boxes=[(0, address_type.encode(self.user_account.signing_address))],
        ).return_value

    async def test_lookup_app(self):
        service = OysterPackWalletConnectService(
            wallet_connect_service_app_id=AppId(self.wallet_connect_service_app_id),
            executor=self.executor,
            algod_client=self.algod_client,
        )

        self.assertIsNone(await service.app(AppId(abs(hash(HashableULID())))))

        self.assertIsNone(await service.app(AppId(self.wallet_connect_service_app_id)))
        app = await service.app(AppId(self.wallet_connect_app_id))
        self.assertIsNotNone(app)
        self.assertEqual(self.wallet_connect_app_id, app.app_id)

    async def test_app_keys_registered(self):
        service = OysterPackWalletConnectService(
            wallet_connect_service_app_id=AppId(self.wallet_connect_service_app_id),
            executor=self.executor,
            algod_client=self.algod_client,
        )

        app_keys = AlgoPrivateKey()

        with self.subTest("keys are not registered"):
            self.assertFalse(
                await service.app_keys_registered(
                    app_id=self.wallet_connect_app_id,
                    signing_address=app_keys.signing_address,
                    encryption_address=app_keys.encryption_address,
                )
            )

        with self.subTest("keys are registered"):
            self.wallet_connect_app_admin_client.call(
                wallet_connect_app.register_keys.method_signature(),
                boxes=[(0, decode_address(app_keys.signing_address))],
                signing_address=app_keys.signing_address,
                encryption_address=app_keys.encryption_address,
            )

            self.assertTrue(
                await service.app_keys_registered(
                    app_id=self.wallet_connect_app_id,
                    signing_address=app_keys.signing_address,
                    encryption_address=app_keys.encryption_address,
                )
            )

    async def test_account_app_id(self):
        service = OysterPackWalletConnectService(
            wallet_connect_service_app_id=AppId(self.wallet_connect_service_app_id),
            executor=self.executor,
            algod_client=self.algod_client,
        )

        with self.subTest("registered account"):
            app_id = await service.account_app_id(self.user_account.signing_address)
            self.assertEqual(self.user_account_app_id, app_id)

        with self.subTest("unregistered account"):
            unregistered_account = AlgoPrivateKey()
            app_id = await service.account_app_id(unregistered_account.signing_address)
            self.assertIsNone(app_id)


if __name__ == "__main__":
    unittest.main()
