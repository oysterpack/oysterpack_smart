import pprint
import unittest

import algosdk.abi
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, TransactionWithSigner
from beaker.client import ApplicationClient
from beaker.consts import algo

from oysterpack.algorand import beaker_utils
from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import AppId, Address, MicroAlgos
from oysterpack.algorand.client.transactions.payment import transfer_algo
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
        user_account = AlgoPrivateKey()

        # fund user account
        txn = transfer_algo(
            sender=Address(creator.address),
            receiver=user_account.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params()
        )
        atc = AtomicTransactionComposer()
        atc.add_transaction(TransactionWithSigner(txn, creator.signer))
        atc.execute(self.algod_client, wait_rounds=4)

        app_client = ApplicationClient(
            self.algod_client,
            app=wallet_connect_account.application,
            sender=creator.address,
            signer=creator.signer,
        )
        app_client.create(account=user_account.signing_address)
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
            sender=user_account.signing_address,
            signer=user_account,
            boxes=[(0, app_id)]
        )

        # ASSERT
        uint64_type = algosdk.abi.uint_type.UintType(64)
        box_contents = app_client.get_box_contents(uint64_type.encode(app_id))
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
            boxes=[(0, uint64_type.encode(app_id))],
        ).return_value
        pprint.pp(keys)
        self.assertEqual(wallet_public_keys.signing_address, keys[0])
        self.assertEqual(wallet_public_keys.encryption_address, keys[1])

        # TODO: try the simulate API
        atc = AtomicTransactionComposer()
        atc.add_method_call(
            sender=user_account.signing_address,
            signer=user_account,
            sp=self.algod_client.suggested_params(),
            app_id=app_client.app_id,
            method=wallet_connect_account.wallet_public_keys.method_spec(),
            method_args=[app_id],
            boxes=[(0, uint64_type.encode(app_id))],
        )
        result = atc.execute(self.algod_client, wait_rounds=4)
        pprint.pp(result.abi_results[0].return_value)


if __name__ == "__main__":
    unittest.main()
