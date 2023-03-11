import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.lookup_auction import (
    LookupAuction,
    AuctionManagerNotRegisteredError,
)
from oysterpack.apps.auction_app.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import AuctionAppId
from tests.algorand.test_support import AlgorandTestCase
from tests.apps.auction_app.commands.data import register_auction_manager


class LookupTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_lookup_auction(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )
        register_auction_manager(
            self.session_factory, seller_auction_manager_client.app_id
        )

        lookup_auction = LookupAuction(
            self.algod_client, LookupAuctionManager(self.session_factory)
        )
        auction = lookup_auction(AuctionAppId(99999999999))
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
            asset_reserve=gold_asset_manager_address,
        )
        # opt in USD$ for the seller account
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve=bid_asset_manager_address,
        )

        min_bid = 10_000
        seller_app_client.set_bid_asset(bid_asset_id, min_bid)
        seller_app_client.optin_asset(gold_asset_id)
        seller_app_client.deposit_asset(gold_asset_id, 10_000)

        # ACT
        auction = lookup_auction(AuctionAppId(seller_app_client.app_id))
        self.assertEqual(seller_app_client.app_id, auction.app_id)

        # cancel, finalize, and delete the auction
        seller_app_client.cancel()
        seller_app_client.finalize()
        creator_app_client.delete_finalized_auction(seller_app_client.app_id)

        auction = lookup_auction(AuctionAppId(seller_app_client.app_id))
        self.assertIsNone(auction)

        with self.subTest("AuctionManager is not registered"):
            # create a new AuctionManager that is not registered in the database
            creator_app_client = create_auction_manager(
                algod_client=self.algod_client,
                signer=creator.signer,
            )
            seller_auction_manager_client = creator_app_client.copy(
                sender=Address(seller.address), signer=seller.signer
            )
            seller_app_client = seller_auction_manager_client.create_auction()

            with self.assertRaises(AuctionManagerNotRegisteredError):
                lookup_auction(seller_app_client.app_id)


if __name__ == "__main__":
    unittest.main()
