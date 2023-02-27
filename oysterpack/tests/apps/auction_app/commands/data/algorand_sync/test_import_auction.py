import unittest

from beaker import sandbox
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.lookup_auction import (
    LookupAuction,
)
from oysterpack.apps.auction_app.commands.data.algorand_sync.import_auction import (
    ImportAuction,
)
from oysterpack.apps.auction_app.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction_app.commands.data.queries.get_auction import GetAuction
from oysterpack.apps.auction_app.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.data.auction import TAuction
from tests.algorand.test_support import AlgorandTestCase
from tests.apps.auction_app.commands.data import create_auctions
from tests.apps.auction_app.commands.data import register_auction_manager


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
        self.get_auction = GetAuction(self.session_factory)

    def setup_contracts(self):
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        self.creator_auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        register_auction_manager(
            self.session_factory, self.creator_auction_manager_client.app_id
        )

        self.seller_auction_manager_client = self.creator_auction_manager_client.copy(
            sender=Address(seller.address),
            signer=seller.signer,
        )

        self.app_ids = []
        for _ in range(5):
            self.app_ids.append(
                self.seller_auction_manager_client.create_auction().app_id
            )

    def tearDown(self) -> None:
        close_all_sessions()

    def test_import_auctions(self):
        for auction_app_id in self.app_ids:
            self.import_auction(auction_app_id)

        with self.session_factory() as session:
            # pylint: disable=not-callable
            auction_count = session.scalar(select(func.count(TAuction.app_id)))
            self.assertEqual(len(self.app_ids), auction_count)

        with self.subTest("Auction exists in database but not on Algorand"):
            # SETUP
            # create auction directly in the database
            auctions = create_auctions(
                auction_manager_app_id=self.creator_auction_manager_client.app_id,
                auction_app_id_start_at=999999,
                count=1,
            )
            self.store_auctions(auctions)
            # verify that the auction exists in the database
            self.assertIsNotNone(self.get_auction(auctions[0].app_id))
            # when the auction does not exist on Algorand, but exists in the database
            # then the import will delete the auction from the database
            self.import_auction(auctions[0].app_id)
            # verify that the auction was deleted from the database
            self.assertIsNone(self.get_auction(auctions[0].app_id))


if __name__ == "__main__":
    unittest.main()
