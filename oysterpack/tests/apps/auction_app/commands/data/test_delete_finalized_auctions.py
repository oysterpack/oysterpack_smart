import unittest

from beaker import sandbox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.app_exists import (
    AppExists,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auctions import (
    SearchAuctions as SearchAuctionsOnAlgorand,
)
from oysterpack.apps.auction_app.commands.data.algorand_sync.import_auctions import (
    ImportAuctions,
    ImportAuctionsRequest,
)
from oysterpack.apps.auction_app.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction_app.commands.data.delete_finalized_autions import (
    DeleteFinalizedAuctions,
)
from oysterpack.apps.auction_app.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction_app.commands.data.queries.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
    AuctionSearchFilters,
)
from oysterpack.apps.auction_app.commands.data.register_auction_manager import (
    RegisterAuctionManager,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from tests.algorand.test_support import AlgorandTestCase


class DeleteFinalizedAuctionsTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.delete_auctions = DeleteAuctions(self.session_factory)
        self.app_exists = AppExists(self.algod_client)

        self.register_auction_manager = RegisterAuctionManager(self.session_factory)
        self.search_auctions_on_algorand = SearchAuctionsOnAlgorand(
            self.indexer, self.algod_client
        )
        self.get_max_auction_app_id = GetMaxAuctionAppId(self.session_factory)
        self.import_auctions = ImportAuctions(
            search=self.search_auctions_on_algorand,
            store=self.store_auctions,
            get_max_auction_app_id=self.get_max_auction_app_id,
        )

        self.search_auctions = SearchAuctions(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_delete_finalized_auction(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        auction_manager_app_id = AuctionManagerAppId(auction_manager_client.app_id)
        self.register_auction_manager(auction_manager_app_id)

        seller_app_client = auction_manager_client.copy(signer=seller.signer)
        seller_auction_client = seller_app_client.create_auction()
        seller_auction_client.cancel()
        seller_auction_client.finalize()

        self.import_auctions(ImportAuctionsRequest(auction_manager_app_id))

        # ACT
        delete_finalized_auctions = DeleteFinalizedAuctions(
            search_auctions=self.search_auctions,
            delete_auctions=self.delete_auctions,
            app_exists=self.app_exists,
            auction_manager_client=auction_manager_client,
        )
        delete_finalized_auctions(auction_manager_app_id)

        # ASSERT
        search_result = self.search_auctions(
            AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    auction_manager_app_id={auction_manager_app_id},
                    status={AuctionStatus.FINALIZED},
                )
            )
        )
        self.assertEqual(0, search_result.total_count)


if __name__ == "__main__":
    unittest.main()
