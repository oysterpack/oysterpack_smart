import unittest

from algosdk.error import AlgodHTTPError
from beaker import sandbox
from beaker.consts import algo

from oysterpack.apps.auction_app.client.auction_client import AuctionClient
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

        # fund the auction to pay for storage
        seller_app_client.fund(int(0.2 * algo))

        bid_asset_id, _asset_manager_address = self.create_test_asset("USD$")
        min_bid = 1_000_000

        with self.subTest("only the seller can set the bid asset"):
            with self.assertRaises(AlgodHTTPError):
                creator_app_client.set_bid_asset(bid_asset_id, min_bid)

        with self.subTest("the bid can be set when the auction status is new"):
            seller_app_client.set_bid_asset(
                bid_asset_id,
                min_bid,
            )
            # ASSERT
            app_state = creator_app_client.get_application_state()
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
            app_state = seller_app_client.get_application_state()
            self.assertEqual(bid_asset_id, app_state.bid_asset_id)
            self.assertEqual(min_bid * 2, app_state.min_bid)

        with self.subTest("change the bid asset settings"):
            bid_asset_id, _asset_manager_address = self.create_test_asset("goUSD")
            min_bid = 2_000_000
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)

            app_state = seller_app_client.get_application_state()
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

        # fund the auction to pay for storage
        seller_app_client.fund(int(0.2 * algo))

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


if __name__ == "__main__":
    unittest.main()
