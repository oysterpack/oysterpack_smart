import pprint
import unittest

import algosdk.abi
from beaker.client import ApplicationClient
from beaker.consts import algo

from oysterpack.algorand import beaker_utils
from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import AppId
from oysterpack.apps.wallet_connect.contracts import wallet_connect_account, wallet_connect_app
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
        # SETUP
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
        app_client.fund(1 * algo)

        def create_app() -> AppId:
            accounts = self.get_sandbox_accounts()
            admin = accounts.pop()

            app_client = ApplicationClient(self.algod_client, app=wallet_connect_app.app)

            name = "Foo"
            url = "https://foo.com"
            enabled = True

            app_id, _app_address, _txid = app_client.create(
                sender=creator.address,
                signer=creator.signer,
                name=name,
                url=url,
                enabled=enabled,
                admin=admin.address,
            )
            return AppId(app_id)

        wallet_private_key = AlgoPrivateKey()
        wallet_public_keys = wallet_private_key.public_keys
        app_id = create_app()

        # ACT
        app_client.call(
            wallet_connect_account.connect_app.method_signature(),
            app=app_id,
            wallet_public_keys=(wallet_public_keys.signing_address, wallet_public_keys.encryption_address),
            boxes=[(0, app_id)]
        )

        # ASSERT
        box_contents = app_client.get_box_contents(algosdk.abi.uint_type.UintType(64).encode(app_id))
        wallet_public_keys_tuple = algosdk.abi.TupleType([
            algosdk.abi.address_type.AddressType(),
            algosdk.abi.address_type.AddressType()
        ])
        keys = wallet_public_keys_tuple.decode(box_contents)
        self.assertEqual(wallet_public_keys.signing_address, keys[0])
        self.assertEqual(wallet_public_keys.encryption_address, keys[1])

        keys = app_client.call(
            wallet_connect_account.wallet_public_keys.method_signature(),
            app=app_id,
            boxes=[(0, app_id)],
        ).return_value
        pprint.pp(keys)
        self.assertEqual(wallet_public_keys.signing_address, keys[0])
        self.assertEqual(wallet_public_keys.encryption_address, keys[1])


if __name__ == "__main__":
    unittest.main()