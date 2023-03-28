import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction.commands.auction_algorand_search.lookup_auction import (
    LookupAuction,
)
from oysterpack.apps.auction.commands.data.algorand_sync.import_auction import (
    ImportAuction,
)
from oysterpack.apps.auction.commands.data.algorand_sync.refresh_auctions import (
    RefreshAuctions,
)
from oysterpack.apps.auction.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction.commands.data.errors import (
    AuctionManagerNotRegisteredError,
)
from oysterpack.apps.auction.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.domain.auction import Auction, AuctionAppId
from tests.algorand.test_support import AlgorandTestCase
from tests.apps.auction.commands.data import register_auction_manager


class ImportAuctionTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.setup_database()
        self.setup_contracts()

    def setup_database(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.lookup_auction_manager = LookupAuctionManager(self.session_factory)
        self.lookup_auction = LookupAuction(
            self.algod_client, self.lookup_auction_manager
        )
        self.delete_auctions = DeleteAuctions(self.session_factory)
        self.import_auction = ImportAuction(
            lookup=self.lookup_auction,
            store=self.store_auctions,
            delete=self.delete_auctions,
        )
        self.refresh_auctions = RefreshAuctions(import_auction=self.import_auction)

    def setup_contracts(self):
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        self.creator_auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        register_auction_manager(
            self.session_factory,
            self.creator_auction_manager_client.app_id,
        )

        self.seller_auction_manager_client = self.creator_auction_manager_client.copy(
            sender=Address(seller.address),
            signer=seller.signer,
        )

    def tearDown(self) -> None:
        close_all_sessions()

    def test_refresh_auctions(self):
        with self.subTest("when auctions exist on Algorand but not in the database"):
            app_ids = []
            app_clients = []
            for _ in range(5):
                app_client = self.seller_auction_manager_client.create_auction()
                app_clients.append(app_client)
                app_ids.append(app_client.app_id)

            result = self.refresh_auctions(app_ids)
            self.assertEqual(5, len(result))
            for auction_app_id, value in result.items():
                self.assertIn(auction_app_id, app_ids)
                self.assertIsInstance(value, Auction)

        with self.subTest("when auctions have been deleted on Algorand"):
            # finalize and delete an auction
            app_client = app_clients.pop()
            app_client.cancel()
            app_client.finalize()
            self.creator_auction_manager_client.delete_finalized_auction(
                app_client.app_id
            )

            result = self.refresh_auctions(app_ids)
            self.assertEqual(5, len(result))
            for auction_app_id, value in result.items():
                self.assertIn(auction_app_id, app_ids)
                if auction_app_id == app_client.app_id:
                    self.assertIsNone(value)
                else:
                    self.assertIsInstance(value, Auction)

        with self.subTest("when AuctionManager is not registered"):
            # create new Auction from unregistered AuctionManager
            auction_manager_client = create_auction_manager(
                algod_client=self.algod_client,
                signer=self.get_sandbox_accounts().pop().signer,
            )
            auction_client = auction_manager_client.create_auction()

            result = self.refresh_auctions([AuctionAppId(auction_client.app_id)])
            self.assertEqual(1, len(result))
            self.assertIsInstance(
                result[auction_client.app_id], AuctionManagerNotRegisteredError
            )


if __name__ == "__main__":
    unittest.main()
