import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction_app.commands.data.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest, AuctionSort, AuctionSortField,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.data import Base
from tests.apps.auction_app.commands.data import create_auctions
from tests.test_support import OysterPackTestCase


class SearchAuctionsTestCase(OysterPackTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.search_auction = SearchAuctions(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_search_with_no_filters_no_sorts(self):
        logger = super().get_logger("test_search_with_no_filters_no_sorts")
        auction_count = 100
        auctions = create_auctions(auction_count)
        self.store_auctions(auctions)

        # page through auctions
        search_request = AuctionSearchRequest(limit=10)
        search_result = self.search_auction(search_request)
        logger.info(
            f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
        )
        self.assertEqual(auction_count, search_result.total_count)
        self.assertEqual(search_request.limit, len(search_result.auctions))
        auctions_retrieved_from_search = search_result.auctions

        while len(auctions_retrieved_from_search) < auction_count:
            search_request = AuctionSearchRequest(
                limit=10,
                offset=search_request.offset + len(search_result.auctions),
            )
            logger.info(f"search_request: {search_request}")
            search_result = self.search_auction(search_request)
            self.assertEqual(auction_count, search_result.total_count)
            self.assertEqual(search_request.limit, len(search_result.auctions))
            auctions_retrieved_from_search += search_result.auctions
            logger.info(
                f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
            )

        self.assertEqual(auction_count, len(auctions_retrieved_from_search))
        # check that all the auctions were returned
        auction_ids_1 = {auction.app_id for auction in auctions}
        auction_ids_2 = {auction.app_id for auction in auctions_retrieved_from_search}
        self.assertEqual(0, len(auction_ids_1 - auction_ids_2))
        for auction in auctions_retrieved_from_search:
            self.assertTrue(auction in auctions)

    def test_search_sort_with_no_filters(self):
        logger = super().get_logger("test_search_sort_with_no_filters")
        auction_count = 100
        auctions = create_auctions(auction_count)
        self.store_auctions(auctions)

        # page through auctions
        search_request = AuctionSearchRequest(limit=10, sort=AuctionSort(
            field=AuctionSortField.AuctionId,
            asc=False,
        ))
        search_result = self.search_auction(search_request)
        logger.info(
            f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
        )
        self.assertEqual(auction_count, search_result.total_count)
        self.assertEqual(search_request.limit, len(search_result.auctions))
        auctions_retrieved_from_search = search_result.auctions

        while len(auctions_retrieved_from_search) < auction_count:
            search_request = AuctionSearchRequest(
                sort=AuctionSort(field=AuctionSortField.AuctionId, asc=False),
                limit=10,
                offset=search_request.offset + len(search_result.auctions),
            )
            logger.info(f"search_request: {search_request}")

            search_result = self.search_auction(search_request)
            self.assertEqual(auction_count, search_result.total_count)
            self.assertEqual(search_request.limit, len(search_result.auctions))
            auctions_retrieved_from_search += search_result.auctions
            logger.info(
                f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
            )

        self.assertEqual(auction_count, len(auctions_retrieved_from_search))
        auction_ids = [auction.app_id for auction in auctions]
        auction_ids.sort(reverse=True)
        auction_ids_from_search_resutls = [auction.app_id for auction in auctions_retrieved_from_search]
        for auction_id_1, auction_id_2 in zip(auction_ids, auction_ids_from_search_resutls):
            self.assertEqual(auction_id_1, auction_id_2)


if __name__ == "__main__":
    unittest.main()
