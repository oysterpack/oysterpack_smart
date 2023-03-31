import unittest
from time import sleep

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction.commands.auction_algorand_search.app_exists import (
    AppExists,
)
from oysterpack.apps.auction.commands.auction_algorand_search.search_auctions import (
    SearchAuctions as SearchAuctionsOnAlgorand,
)
from oysterpack.apps.auction.commands.data.algorand_sync.import_auctions import (
    ImportAuctions,
    ImportAuctionsRequest,
)
from oysterpack.apps.auction.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction.commands.data.delete_finalized_autions import (
    DeleteFinalizedAuctions,
    DeleteFinalizedAuctionsRequest,
)
from oysterpack.apps.auction.commands.data.errors import (
    AuctionManagerNotRegisteredError,
)
from oysterpack.apps.auction.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction.commands.data.queries.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
    AuctionSearchFilters,
)
from oysterpack.apps.auction.commands.data.register_auction_manager import (
    RegisterAuctionManager,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.domain.auction import AuctionManagerAppId
from tests.algorand.test_support import AlgorandTestCase


@unittest.skip("beaker upgrade broke contracts")
class DeleteFinalizedAuctionsTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.delete_auctions = DeleteAuctions(self.session_factory)
        self.lookup_auction_manager = LookupAuctionManager(self.session_factory)
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

    def test_delete_finalized_auctions(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        auction_manager_app_id = AuctionManagerAppId(auction_manager_client.app_id)

        request = DeleteFinalizedAuctionsRequest(
            auction_manager_app_id=auction_manager_app_id
        )

        delete_finalized_auctions = DeleteFinalizedAuctions(
            search_auctions=self.search_auctions,
            delete_auctions=self.delete_auctions,
            app_exists=self.app_exists,
            lookup_auction_manager=self.lookup_auction_manager,
            auction_manager_client=auction_manager_client,
        )

        seller_app_client = auction_manager_client.copy(signer=seller.signer)
        seller_auction_client = seller_app_client.create_auction()
        seller_auction_client.cancel()
        seller_auction_client.finalize()
        sleep(1)  # give indexer time to index

        with self.subTest("when AuctionManager is not registered"):
            with self.assertRaises(AuctionManagerNotRegisteredError):
                delete_finalized_auctions(request)

        self.register_auction_manager(auction_manager_app_id)

        with self.subTest("when request batch size <= 0"):
            with self.assertRaises(AssertionError) as err:
                delete_finalized_auctions(
                    DeleteFinalizedAuctionsRequest(
                        auction_manager_app_id=auction_manager_app_id,
                        batch_size=0,
                    )
                )
            self.assertIn("`batch_size` must be greater than zero", str(err.exception))

        with self.subTest("when auctions have not yet been imported into the database"):
            delete_count = delete_finalized_auctions(request)
            self.assertEqual(0, delete_count)

        with self.subTest("after importing the auctions into the database"):
            self.import_auctions(ImportAuctionsRequest(auction_manager_app_id))
            # verify that finalized auction has been imported
            search_result = self.search_auctions(
                AuctionSearchRequest(
                    filters=AuctionSearchFilters(
                        auction_manager_app_id={auction_manager_app_id},
                        status={AuctionStatus.FINALIZED},
                    )
                )
            )
            self.assertEqual(1, search_result.total_count)

            # ACT
            delete_count = delete_finalized_auctions(request)
            self.assertEqual(1, delete_count)

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

    def test_delete_finalized_auctions_batch_size(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        auction_manager_app_id = AuctionManagerAppId(auction_manager_client.app_id)

        request = DeleteFinalizedAuctionsRequest(
            auction_manager_app_id=auction_manager_app_id, batch_size=2
        )

        delete_finalized_auctions = DeleteFinalizedAuctions(
            search_auctions=self.search_auctions,
            delete_auctions=self.delete_auctions,
            app_exists=self.app_exists,
            lookup_auction_manager=self.lookup_auction_manager,
            auction_manager_client=auction_manager_client,
        )

        seller_app_client = auction_manager_client.copy(signer=seller.signer)

        # create 5 finalized auctions
        finalized_auction_count = 5
        for _ in range(finalized_auction_count):
            seller_auction_client = seller_app_client.create_auction()
            seller_auction_client.cancel()
            seller_auction_client.finalize()

        sleep(1)  # give indexer time to index

        self.register_auction_manager(auction_manager_app_id)

        self.import_auctions(ImportAuctionsRequest(auction_manager_app_id))
        # verify that finalized auction has been imported
        search_result = self.search_auctions(
            AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    auction_manager_app_id={auction_manager_app_id},
                    status={AuctionStatus.FINALIZED},
                )
            )
        )
        self.assertEqual(finalized_auction_count, search_result.total_count)

        # ACT
        delete_count = delete_finalized_auctions(request)
        self.assertEqual(finalized_auction_count, delete_count)

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

    def test_delete_finalized_auctions_not_exists_on_algorand(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        auction_manager_app_id = AuctionManagerAppId(auction_manager_client.app_id)

        request = DeleteFinalizedAuctionsRequest(
            auction_manager_app_id=auction_manager_app_id
        )

        delete_finalized_auctions = DeleteFinalizedAuctions(
            search_auctions=self.search_auctions,
            delete_auctions=self.delete_auctions,
            app_exists=self.app_exists,
            lookup_auction_manager=self.lookup_auction_manager,
        )

        seller_app_client = auction_manager_client.copy(signer=seller.signer)
        seller_auction_client = seller_app_client.create_auction()
        seller_auction_client.cancel()
        seller_auction_client.finalize()
        sleep(1)  # give indexer time to index

        self.register_auction_manager(auction_manager_app_id)
        self.import_auctions(ImportAuctionsRequest(auction_manager_app_id))
        # verify that finalized auction has been imported
        search_result = self.search_auctions(
            AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    auction_manager_app_id={auction_manager_app_id},
                    status={AuctionStatus.FINALIZED},
                )
            )
        )
        self.assertEqual(1, search_result.total_count)

        # delete finalized auction from Algorand
        auction_manager_client.delete_finalized_auction(seller_auction_client.app_id)
        sleep(1)  # give indexer time to index

        # ACT
        delete_count = delete_finalized_auctions(request)
        self.assertEqual(1, delete_count)

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
