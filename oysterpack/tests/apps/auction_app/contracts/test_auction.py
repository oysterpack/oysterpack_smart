import unittest

from algosdk.transaction import wait_for_confirmation
from beaker import sandbox

from oysterpack.algorand.client.model import Address
from oysterpack.algorand.client.transactions import assets
from oysterpack.apps.auction_app.client.auction_client import AuctionClient, AuthError
from oysterpack.apps.auction_app.contracts.auction import (
    Auction,
    AuctionStatus,
)
from tests.algorand.test_support import AlgorandTestSupport


class AuctionTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_create(self):
        # SETUP
        logger = super().get_logger("test_create")

        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )

        # ACT
        creator_app_client.create(seller=seller.address)
        auction_client = AuctionClient.from_client(creator_app_client)

        # ASSERT
        app_state = creator_app_client.get_application_state()
        logger.info(f"app_state: {app_state}")
        self.assertEqual(seller.address, auction_client.get_seller_address())
        self.assertEqual(app_state[Auction.status.str_key()], AuctionStatus.New.value)

    def test_set_bid_asset(self):
        # SETUP
        logger = super().get_logger("test_set_bid_asset")

        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient.from_client(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient.from_client(creator_app_client)

        bid_asset_id, _asset_manager_address = self.create_test_asset("USD$")
        min_bid = 1_000_000

        with self.subTest("only the seller can set the bid asset"):
            with self.assertRaises(AuthError):
                creator_app_client.set_bid_asset(bid_asset_id, min_bid)

        with self.subTest("the bid can be set when the auction status is new"):
            seller_app_client.set_bid_asset(
                bid_asset_id,
                min_bid,
            )
            # ASSERT
            app_state = creator_app_client.get_auction_state()
            logger.info(f"app_state: {app_state}")
            self.assertEqual(app_state.bid_asset_id, bid_asset_id)
            self.assertEqual(app_state.min_bid, min_bid)

            app_assets = seller_app_client.get_application_account_info()["assets"]
            self.assertEqual(len(app_assets), 1)
            self.assertEqual(
                len(
                    [asset for asset in app_assets if asset["asset-id"] == bid_asset_id]
                ),
                1,
            )

        with self.subTest("setting the bid asset again to the same values is a noop "):
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)

        with self.subTest("update the min bid"):
            seller_app_client.set_bid_asset(bid_asset_id, min_bid * 2)
            app_state = seller_app_client.get_auction_state()
            self.assertEqual(bid_asset_id, app_state.bid_asset_id)
            self.assertEqual(min_bid * 2, app_state.min_bid)

        with self.subTest("change the bid asset settings"):
            bid_asset_id, _asset_manager_address = self.create_test_asset("goUSD")
            min_bid = 2_000_000
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)

            app_state = seller_app_client.get_auction_state()
            self.assertEqual(bid_asset_id, app_state.bid_asset_id)
            self.assertEqual(min_bid, app_state.min_bid)

            app_assets = seller_app_client.get_application_account_info()["assets"]
            self.assertEqual(len(app_assets), 1)
            self.assertEqual(
                len(
                    [asset for asset in app_assets if asset["asset-id"] == bid_asset_id]
                ),
                1,
            )

    def test_optout_asset(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient.from_client(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient.from_client(creator_app_client)

        bid_asset_id, _asset_manager_address = self.create_test_asset("USD$")
        min_bid = 1_000_000
        seller_app_client.set_bid_asset(bid_asset_id, min_bid)

        # ACT
        seller_app_client.optout_asset(bid_asset_id)
        app_account_info = seller_app_client.get_application_account_info()
        self.assertEqual(len(app_account_info["assets"]), 0)

        with self.subTest(
                "after opting out the bid asset, the bid asset can be set again"
        ):
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)
            app_account_info = seller_app_client.get_application_account_info()
            self.assertEqual(len(app_account_info["assets"]), 1)
            self.assertEqual(app_account_info["assets"][0]["asset-id"], bid_asset_id)

        with self.subTest("only the seller can optout an asset"):
            with self.assertRaises(AuthError):
                creator_app_client.optout_asset(bid_asset_id)

    def test_optin_asset(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient.from_client(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient.from_client(creator_app_client)

        gold_asset_id, _asset_manager_address = self.create_test_asset("GOLD$")

        # auction should start with zero assets
        auction_assets = seller_app_client.get_auction_assets()
        self.assertEqual(len(auction_assets), 0)

        # ACT
        with self.subTest("only the seller can optin an asset"):
            with self.assertRaises(AuthError):
                creator_app_client.optin_asset(gold_asset_id)

        seller_app_client.optin_asset(gold_asset_id)
        # ASSERT asset was opted in
        auction_assets = seller_app_client.get_auction_assets()
        self.assertEqual(len(auction_assets), 1)
        self.assertEqual(
            len([asset for asset in auction_assets if asset.asset_id == gold_asset_id]),
            1,
        )

        with self.subTest("opting is an asset that is already opted in is a noop"):
            seller_app_client.optin_asset(gold_asset_id)

        with self.subTest("optin a second asset"):
            go_mint_asset_id, _asset_manager_address = self.create_test_asset("goMINT")
            seller_app_client.optin_asset(go_mint_asset_id)
            # Assert
            auction_assets = seller_app_client.get_auction_assets()
            self.assertEqual(len(auction_assets), 2)
            self.assertEqual(
                len(
                    [
                        asset
                        for asset in auction_assets
                        if asset.asset_id == gold_asset_id
                    ]
                ),
                1,
            )
            self.assertEqual(
                len(
                    [
                        asset
                        for asset in auction_assets
                        if asset.asset_id == go_mint_asset_id
                    ]
                ),
                1,
            )



    def test_deposit_asset(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient.from_client(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient.from_client(creator_app_client)

        gold_asset_id, asset_manager_address = self.create_test_asset("GOLD$")

        # opt in GOLD$ for the seller account
        txn = assets.opt_in(
            account=Address(seller.address),
            asset_id=gold_asset_id,
            suggested_params=self.algod_client.suggested_params,
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # transfer assets to the seller account
        txn = assets.transfer(
            sender=asset_manager_address,
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=1_000_000,
            suggested_params=self.algod_client.suggested_params,
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # ACT
        deposit_amount = 10_000
        asset_holding = seller_app_client.deposit_asset(gold_asset_id, deposit_amount)
        self.assertEqual(asset_holding.asset_id, gold_asset_id)
        self.assertEqual(asset_holding.amount, deposit_amount)

        with self.subTest("only the seller can deposit assets"):
            with self.assertRaises(AuthError):
                creator_app_client.deposit_asset(gold_asset_id, deposit_amount)

if __name__ == "__main__":
    unittest.main()
