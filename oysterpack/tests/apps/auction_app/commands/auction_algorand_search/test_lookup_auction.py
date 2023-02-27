import unittest

from beaker import sandbox

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.lookup_auction import (
    LookupAuction,
    LookupAuctionRequest,
)
from oysterpack.apps.auction_app.domain.auction import AuctionAppId, AuctionManagerAppId
from tests.algorand.test_support import AlgorandTestCase


class LookupTestCase(AlgorandTestCase):
    def test_lookup_auction(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )

        lookup_auction = LookupAuction(self.algod_client)
        auction = lookup_auction(
            LookupAuctionRequest(
                AuctionAppId(99999999999),
                AuctionManagerAppId(creator_app_client.app_id),
            )
        )
        self.assertIsNone(auction)

        seller_app_client = seller_auction_manager_client.create_auction()

        gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
        bid_asset_id, bid_asset_manager_address = self.create_test_asset("USD$")

        # opt in GOLD$ for the seller account
        starting_asset_balance = 1_000_000
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=gold_asset_manager_address,
        )
        # opt in USD$ for the seller account
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )

        min_bid = 10_000
        seller_app_client.set_bid_asset(bid_asset_id, min_bid)
        seller_app_client.optin_asset(gold_asset_id)
        seller_app_client.deposit_asset(gold_asset_id, 10_000)

        # ACT
        auction = lookup_auction(
            LookupAuctionRequest(
                AuctionAppId(seller_app_client.app_id),
                AuctionManagerAppId(creator_app_client.app_id),
            )
        )
        self.assertEqual(seller_app_client.app_id, auction.app_id)

        # cancel, finalize, and delete the auction
        seller_app_client.cancel()
        seller_app_client.finalize()
        creator_app_client.delete_finalized_auction(seller_app_client.app_id)

        auction = lookup_auction(
            LookupAuctionRequest(
                AuctionAppId(seller_app_client.app_id),
                AuctionManagerAppId(creator_app_client.app_id),
            )
        )
        self.assertIsNone(auction)


if __name__ == "__main__":
    unittest.main()
