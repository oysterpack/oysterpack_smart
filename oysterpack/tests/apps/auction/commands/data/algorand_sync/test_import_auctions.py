import unittest
from time import sleep

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
)
from oysterpack.apps.auction.commands.data.algorand_sync.import_auctions import (
    ImportAuctions,
    ImportAuctionsRequest,
)
from oysterpack.apps.auction.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.data.auction import TAuction
from tests.algorand.test_support import AlgorandTestCase
from tests.apps.auction.commands.data import register_auction_manager


class ImportAuctionsTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.setup_database()
        self.setup_contracts()

    def setup_database(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.get_max_auction_app_id = GetMaxAuctionAppId(self.session_factory)

    def setup_contracts(self):
        accounts = self.get_sandbox_accounts()
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
        sleep(1)  # give the indexer time to index

    def tearDown(self) -> None:
        close_all_sessions()

    def test_import_auctions(self):
        logger = self.get_logger("test_import_auctions")
        import_auctions = ImportAuctions(
            search=SearchAuctions(
                indexer_client=self.indexer, algod_client=self.algod_client
            ),
            store=self.store_auctions,
            get_max_auction_app_id=self.get_max_auction_app_id,
        )

        import_auctions_request = ImportAuctionsRequest(
            auction_manager_app_id=self.seller_auction_manager_client.app_id,
            batch_size=2,
        )

        imported_count = 0
        while imported_auctions := import_auctions(import_auctions_request):
            imported_count += len(imported_auctions)
            logger.info(imported_auctions)
            with self.session_factory() as session:
                # pylint: disable=not-callable
                auction_count = session.scalar(select(func.count(TAuction.app_id)))
                self.assertEqual(imported_count, auction_count)

        with self.session_factory() as session:
            # pylint: disable=not-callable
            auction_count = session.scalar(select(func.count(TAuction.app_id)))
            self.assertEqual(len(self.app_ids), auction_count)


if __name__ == "__main__":
    unittest.main()
