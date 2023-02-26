import unittest
from time import sleep

from beaker import sandbox
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
)
from oysterpack.apps.auction_app.commands.data.algorand_sync.import_auctions import (
    ImportAuctions,
    ImportAuctionsRequest,
)
from oysterpack.apps.auction_app.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.data.auction import TAuction
from tests.algorand.test_support import AlgorandTestCase


class MyTestCase(AlgorandTestCase):
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
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        self.creator_auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
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
        import_auctions = ImportAuctions(
            search=SearchAuctions(
                indexer_client=self.indexer, algod_client=self.algod_client
            ),
            store=self.store_auctions,
            get_max_auction_app_id=self.get_max_auction_app_id,
        )

        import_auctions_request = ImportAuctionsRequest(
            auction_manager_app_id=self.seller_auction_manager_client.app_id,
            algorand_search_limit=2,
        )
        import_auctions(import_auctions_request)
        with self.session_factory() as session:
            # pylint: disable=not-callable
            auction_count = session.scalar(select(func.count(TAuction.app_id)))
            self.assertEqual(len(self.app_ids), auction_count)

        # create more auctions
        for _ in range(5):
            self.app_ids.append(
                self.seller_auction_manager_client.create_auction().app_id
            )
        sleep(1)

        import_auctions(import_auctions_request)
        with self.session_factory() as session:
            # pylint: disable=not-callable
            auction_count = session.scalar(select(func.count(TAuction.app_id)))
            self.assertEqual(len(self.app_ids), auction_count)


if __name__ == "__main__":
    unittest.main()
