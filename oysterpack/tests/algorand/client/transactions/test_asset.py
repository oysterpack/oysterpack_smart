import unittest

from algosdk.account import generate_account
from algosdk.encoding import base64
from algosdk.transaction import wait_for_confirmation

from oysterpack.algorand.client.accounts import Address, get_asset_holding
from oysterpack.algorand.client.transactions import asset
from tests.algorand.test_support import AlgorandTestCase


class AssetsTestCase(AlgorandTestCase):
    def metadata_hash(self) -> bytes:
        import hashlib

        m = hashlib.sha256()
        m.update(b"asset metadata")
        return m.digest()

    def create_asset(self) -> tuple[asset.AssetId, Address]:
        """
        Creates a new asset using the first account in the sandbox default wallet as the administrative accounts.

        Returns (AssetId, manager account address)
        """
        sender = self.sandbox_default_wallet.list_keys()[0]
        manager = reserve = freeze = clawback = sender
        total_base_units = 1_000_000_000_000_000
        decimals = 6
        asset_name = "GOLD"
        unit_name = "GLD"
        url = "https://meld.gold/"
        txn = asset.create(
            sender=sender,
            manager=manager,
            reserve=reserve,
            freeze=freeze,
            clawback=clawback,
            asset_name=asset_name,
            unit_name=unit_name,
            url=url,
            metadata_hash=self.metadata_hash(),
            total_base_units=total_base_units,
            decimals=decimals,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        tx_info = wait_for_confirmation(
            algod_client=self.algod_client, txid=txid, wait_rounds=4
        )
        return (asset.AssetId(tx_info["asset-index"]), Address(manager))

    def test_create(self):
        sender = self.sandbox_default_wallet.list_keys()[0]
        _, manager = generate_account()
        _, reserve = generate_account()
        _, freeze = generate_account()
        _, clawback = generate_account()
        total_base_units = 1_000_000_000_000_000
        decimals = 6
        asset_name = "GOLD"
        unit_name = "GLD"
        url = "https://meld.gold/"
        txn = asset.create(
            sender=sender,
            manager=manager,
            reserve=reserve,
            freeze=freeze,
            clawback=clawback,
            asset_name=asset_name,
            unit_name=unit_name,
            url=url,
            metadata_hash=self.metadata_hash(),
            total_base_units=total_base_units,
            decimals=decimals,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        tx_info = wait_for_confirmation(
            algod_client=self.algod_client, txid=txid, wait_rounds=4
        )
        # check that the transaction had a lease set
        self.assertTrue(len(tx_info["txn"]["txn"]["lx"]) > 0)

        # check that the asset was created
        asset_id = tx_info["asset-index"]
        asset_info = self.algod_client.asset_info(asset_id)
        # check the asset config params were set correct
        self.assertEqual(
            asset_info["params"]["metadata-hash"],
            base64.b64encode(self.metadata_hash()).decode(),
        )
        self.assertEqual(asset_info["params"]["creator"], sender)
        self.assertEqual(asset_info["params"]["manager"], manager)
        self.assertEqual(asset_info["params"]["reserve"], reserve)
        self.assertEqual(asset_info["params"]["clawback"], clawback)
        self.assertEqual(asset_info["params"]["freeze"], freeze)
        self.assertEqual(asset_info["params"]["total"], total_base_units)
        self.assertEqual(asset_info["params"]["decimals"], decimals)
        self.assertFalse(asset_info["params"]["default-frozen"])
        self.assertEqual(asset_info["params"]["name"], asset_name)
        self.assertEqual(asset_info["params"]["unit-name"], unit_name)
        self.assertEqual(asset_info["params"]["url"], url)

        # check that the sender account has the asset listed as created
        sender_info = self.algod_client.account_info(sender)
        account_created_asset_ids = [
            asset["index"] for asset in sender_info["created-assets"]
        ]
        self.assertTrue(asset_id in account_created_asset_ids)

    def test_update(self):
        asset_id, manager = self.create_asset()

        # update the asset by changing all the asset accounts
        _, new_manager = generate_account()
        _, reserve = generate_account()
        _, freeze = generate_account()
        _, clawback = generate_account()
        txn = asset.update(
            sender=manager,
            asset_id=asset_id,
            manager=new_manager,
            reserve=reserve,
            freeze=freeze,
            clawback=clawback,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        tx_info = wait_for_confirmation(
            algod_client=self.algod_client, txid=txid, wait_rounds=4
        )
        # check that the transaction had a lease set
        self.assertTrue(len(tx_info["txn"]["txn"]["lx"]) > 0)

        # check the config changes
        asset_info = self.algod_client.asset_info(asset_id)
        self.assertEqual(asset_info["params"]["manager"], new_manager)
        self.assertEqual(asset_info["params"]["reserve"], reserve)
        self.assertEqual(asset_info["params"]["clawback"], clawback)
        self.assertEqual(asset_info["params"]["freeze"], freeze)

    def test_opt_in(self):
        asset_id, _manager = self.create_asset()
        account = self.sandbox_default_wallet.list_keys()[1]
        txn = asset.opt_in(
            account=account,
            asset_id=asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        tx_info = wait_for_confirmation(
            algod_client=self.algod_client, txid=txid, wait_rounds=4
        )
        # check that the transaction had a lease set
        self.assertTrue(len(tx_info["txn"]["txn"]["lx"]) > 0)

        self.assertIsNotNone(get_asset_holding(account, asset_id, self.algod_client))

    def test_transfer(self):
        asset_id, manager = self.create_asset()
        account = self.sandbox_default_wallet.list_keys()[1]

        # opt in the account
        txn = asset.opt_in(
            account=account,
            asset_id=asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client=self.algod_client, txid=txid, wait_rounds=4)

        txn = asset.transfer(
            sender=manager,
            receiver=account,
            asset_id=asset_id,
            amount=1000,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        tx_info = wait_for_confirmation(
            algod_client=self.algod_client, txid=txid, wait_rounds=4
        )
        # check that the transaction had a lease set
        self.assertTrue(len(tx_info["txn"]["txn"]["lx"]) > 0)

        account_info = self.algod_client.account_info(account)
        asset_balance = [
            asset["amount"]
            for asset in account_info["assets"]
            if asset["asset-id"] == asset_id
        ][0]
        self.assertEqual(asset_balance, 1000)

    def test_close_out(self):
        asset_id, manager = self.create_asset()
        account = self.sandbox_default_wallet.list_keys()[1]

        # opt in
        txn = asset.opt_in(
            account=account,
            asset_id=asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client=self.algod_client, txid=txid)
        self.assertIsNotNone(get_asset_holding(account, asset_id, self.algod_client))

        # close out
        txn = asset.close_out(
            account=account,
            asset_id=asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client=self.algod_client, txid=txid)

        # check that the account no longer holds the asset
        self.assertIsNone(get_asset_holding(account, asset_id, self.algod_client))

    def test_close_out_to_account(self):
        asset_id, manager = self.create_asset()
        account = self.sandbox_default_wallet.list_keys()[1]

        # opt in
        txn = asset.opt_in(
            account=account,
            asset_id=asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client=self.algod_client, txid=txid, wait_rounds=4)
        self.assertIsNotNone(get_asset_holding(account, asset_id, self.algod_client))

        # close out
        _, close_to = generate_account()
        txn = asset.close_out(
            account=account,
            close_to=close_to,
            asset_id=asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client=self.algod_client, txid=txid, wait_rounds=4)

        # check that the account no longer holds the asset
        self.assertIsNone(get_asset_holding(account, asset_id, self.algod_client))


if __name__ == "__main__":
    unittest.main()
