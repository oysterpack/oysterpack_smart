import unittest

from algosdk.account import generate_account
from algosdk.transaction import wait_for_confirmation

from oysterpack.algorand.client.accounts import get_asset_holdings, get_asset_holding
from oysterpack.algorand.client.transactions import assets
from tests.algorand.test_support import AlgorandTestSupport


class MyTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_get_asset_holdings(self):
        # create asset
        account = self.sandbox_default_wallet.list_keys()[0]
        txn = assets.create(
            sender=account,
            asset_name="GOLD",
            unit_name="GOLD",
            total_base_units=100000000,
            manager=account,
            reserve=account,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        txinfo = wait_for_confirmation(self.algod_client, txid)
        asset_id = txinfo["asset-index"]

        asset_holdings = get_asset_holdings(account, self.algod_client)
        self.assertEqual(
            len(
                list(
                    filter(
                        lambda asset_holding: asset_holding.asset_id == asset_id,
                        asset_holdings,
                    )
                )
            ),
            1,
        )

        with self.subTest(
            "lookup asset holdings for new generated account should return an empty list"
        ):
            _pk, account = generate_account()
            asset_holdings = get_asset_holdings(account, self.algod_client)
            self.assertEqual(asset_holdings, [])

    def test_get_asset_holding(self):
        # create asset
        account = self.sandbox_default_wallet.list_keys()[0]
        txn = assets.create(
            sender=account,
            asset_name="GOLD",
            unit_name="GOLD",
            total_base_units=100000000,
            manager=account,
            reserve=account,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        txinfo = wait_for_confirmation(self.algod_client, txid)
        asset_id = txinfo["asset-index"]

        asset_holding = get_asset_holding(account, asset_id, self.algod_client)
        self.assertEqual(asset_holding.asset_id, asset_id)

        with self.subTest(
            "lookup asset holding for asset that the account does not hold"
        ):
            _pk, account = generate_account()
            asset_holding = get_asset_holding(account, asset_id + 1, self.algod_client)
            self.assertIsNone(asset_holding)

        with self.subTest(
            "lookup asset holding for new generated account should return an empty list"
        ):
            _pk, account = generate_account()
            asset_holding = get_asset_holding(account, asset_id, self.algod_client)
            self.assertIsNone(asset_holding)


if __name__ == "__main__":
    unittest.main()
