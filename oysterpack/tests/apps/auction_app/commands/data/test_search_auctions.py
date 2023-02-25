import unittest
from typing import Tuple, cast

from algosdk.account import generate_account
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address, AssetId
from oysterpack.apps.auction_app.commands.data.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
    AuctionSort,
    AuctionSortField,
    AuctionSearchFilters,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import Auction
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
        auction_count = 101
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

        while search_request := search_request.next_page(search_result):
            logger.info(f"search_request: {search_request}")
            search_result = self.search_auction(search_request)
            self.assertEqual(auction_count, search_result.total_count)
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

    def test_previous_page_navigation(self):
        logger = super().get_logger("test_previous_page_navigation")
        auction_count = 101
        auctions = create_auctions(auction_count)
        self.store_auctions(auctions)

        search_request = AuctionSearchRequest(limit=10, offset=auction_count - 1)
        search_result = self.search_auction(search_request)
        logger.info(
            f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
        )
        auctions_retrieved_from_search = search_result.auctions
        while search_request := search_request.previous_page(search_result):
            logger.info(f"search_request: {search_request}")
            search_result = self.search_auction(search_request)
            self.assertEqual(auction_count, search_result.total_count)
            self.assertEqual(search_request.limit, len(search_result.auctions))
            auctions_retrieved_from_search += search_result.auctions
            logger.info(
                f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
            )

        self.assertEqual(auction_count, len(auctions_retrieved_from_search))

    def test_goto_navigation(self):
        auction_count = 101
        auctions = create_auctions(auction_count)
        self.store_auctions(auctions)

        search_request = AuctionSearchRequest(limit=10, offset=auction_count - 1)
        search_result = self.search_auction(search_request)

        search_request = search_request.goto(search_result, offset=50)
        search_result = self.search_auction(search_request)
        self.assertEqual(51, search_result.auctions[0].app_id)
        self.assertEqual(60, search_result.auctions[-1].app_id)

        search_request = search_request.goto(search_result, offset=0)
        search_result = self.search_auction(search_request)
        self.assertEqual(1, search_result.auctions[0].app_id)
        self.assertEqual(10, search_result.auctions[-1].app_id)

        search_request = search_request.goto(search_result, offset=95)
        search_result = self.search_auction(search_request)
        self.assertEqual(96, search_result.auctions[0].app_id)
        self.assertEqual(101, search_result.auctions[-1].app_id)

        with self.assertRaises(AssertionError) as err:
            search_request.goto(search_result, offset=-1)
        self.assertTrue("offset must be >= 0" in str(err.exception))

        with self.assertRaises(AssertionError) as err:
            search_request.goto(search_result, offset=101)
        self.assertTrue("offset must be < 101" in str(err.exception))

    def test_search_sort_with_no_filters(self):
        logger = super().get_logger("test_search_sort_with_no_filters")
        auction_count = 100
        auctions = create_auctions(auction_count)
        self.store_auctions(auctions)

        # page through auctions
        search_request = AuctionSearchRequest(
            limit=10,
            sort=AuctionSort(
                field=AuctionSortField.AuctionId,
                asc=False,
            ),
        )
        search_result = self.search_auction(search_request)
        logger.info(
            f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
        )
        self.assertEqual(auction_count, search_result.total_count)
        self.assertEqual(search_request.limit, len(search_result.auctions))
        auctions_retrieved_from_search = search_result.auctions

        while search_request := search_request.next_page(search_result):
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
        auction_ids_from_search_resutls = [
            auction.app_id for auction in auctions_retrieved_from_search
        ]
        for auction_id_1, auction_id_2 in zip(
                auction_ids, auction_ids_from_search_resutls
        ):
            self.assertEqual(auction_id_1, auction_id_2)

    def test_filters(self):
        auction_count = 100
        auctions = create_auctions(auction_count)
        self.store_auctions(auctions)

        auction_ids = [auction.app_id for auction in auctions]

        with self.subTest("single Auction ID filter"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(app_id=set(auction_ids[0:1])),
            )
            search_result = self.search_auction(search_request)
            self.assertEqual(1, search_result.total_count)
            self.assertEqual(auctions[0], search_result.auctions[0])

        with self.subTest("multiple Auction ID filter"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(app_id=set(auction_ids[0:5])),
            )
            search_result = self.search_auction(search_request)
            self.assertEqual(5, search_result.total_count)
            self.assertEqual(auctions[0:5], search_result.auctions)

        with self.subTest("single status filter"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(status={AuctionStatus.NEW}),
            )
            search_result = self.search_auction(search_request)
            new_status_count = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.status == AuctionStatus.NEW
                ]
            )
            self.assertEqual(new_status_count, search_result.total_count)
            for auction in search_result.auctions:
                self.assertEqual(AuctionStatus.NEW, auction.state.status)

        with self.subTest("multiple status filter"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    status={AuctionStatus.NEW, AuctionStatus.COMMITTED}
                ),
            )
            search_result = self.search_auction(search_request)
            new_status_count = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.status == AuctionStatus.NEW
                       or auction.state.status == AuctionStatus.COMMITTED
                ]
            )
            self.assertEqual(new_status_count, search_result.total_count)
            for auction in search_result.auctions:
                self.assertTrue(
                    auction.state.status == AuctionStatus.NEW
                    or auction.state.status == AuctionStatus.COMMITTED
                )

        with self.subTest("single seller filter"):
            _private_key, seller_1 = generate_account()
            auctions = create_auctions(5, Address(seller_1))
            self.store_auctions(auctions)

            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(seller={seller_1}),
            )
            search_result = self.search_auction(search_request)
            self.assertEqual(5, search_result.total_count)
            for auction in search_result.auctions:
                self.assertEqual(seller_1, auction.state.seller)

        with self.subTest("multiple seller filter"):
            _private_key, seller_2 = generate_account()
            auctions = create_auctions(10, Address(seller_1))
            self.store_auctions(auctions)
            # updates the first 5 to seller_2
            auctions = create_auctions(5, Address(seller_2))
            self.store_auctions(auctions)

            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(seller={seller_1, seller_2}),
            )
            search_result = self.search_auction(search_request)
            self.assertEqual(10, search_result.total_count)
            for auction in search_result.auctions:
                self.assertTrue(auction.state.seller in {seller_1, seller_2})

    def test_filter_bid_asset(self):
        logger = super().get_logger("test_filter_bid_asset")
        bid_asset_ids = {
            AssetId(50): 0,
            AssetId(60): 0,
            AssetId(70): 0,
        }
        # the total number of auctions created per bid asset ID will match the bid asset ID
        auction_app_id_start_at = 1
        for bid_asset_id in bid_asset_ids.keys():
            auctions = create_auctions(
                count=bid_asset_id,
                bid_asset_id=bid_asset_id,
                auction_app_id_start_at=auction_app_id_start_at,
            )
            bid_asset_ids[bid_asset_id] = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.bid_asset_id == bid_asset_id
                ]
            )
            self.store_auctions(auctions)
            auction_app_id_start_at += bid_asset_id

        logger.info(bid_asset_ids)

        # single value search
        for bid_asset_id in bid_asset_ids:
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(bid_asset_id={bid_asset_id}),
            )
            search_result = self.search_auction(search_request)
            self.assertEqual(bid_asset_ids[bid_asset_id], search_result.total_count)

        # multi-value search
        search_request = AuctionSearchRequest(
            filters=AuctionSearchFilters(bid_asset_id={AssetId(50), AssetId(60)}),
        )
        search_result = self.search_auction(search_request)
        self.assertEqual(
            bid_asset_ids[AssetId(50)] + bid_asset_ids[AssetId(60)],
            search_result.total_count,
        )

    def test_min_bid_filter(self):
        logger = super().get_logger("test_min_bid_filter")
        # SETUP
        # create auctions with different bid assets and min bids

        auctions_by_bid_asset_min_bid: dict[Tuple[AssetId, int], int] = {}  # type: ignore

        def update_counts(auctions: list[Auction]):
            result = self.store_auctions(auctions)
            logger.info(result)
            for auction in auctions:
                if auction.state.bid_asset_id is not None:
                    key = (auction.state.bid_asset_id, cast(int, auction.state.min_bid))
                    if key in auctions_by_bid_asset_min_bid:
                        auctions_by_bid_asset_min_bid[key] += 1
                    else:
                        auctions_by_bid_asset_min_bid[key] = 1

        update_counts(
            create_auctions(
                count=10,
                bid_asset_id=AssetId(50),
                min_bid=100,
                auction_app_id_start_at=1,
            )
        )
        update_counts(
            create_auctions(
                count=20,
                bid_asset_id=AssetId(50),
                min_bid=200,
                auction_app_id_start_at=11,
            )
        )
        update_counts(
            create_auctions(
                count=30,
                bid_asset_id=AssetId(50),
                min_bid=300,
                auction_app_id_start_at=31,
            )
        )
        update_counts(
            create_auctions(
                count=10,
                bid_asset_id=AssetId(60),
                min_bid=100,
                auction_app_id_start_at=61,
            )
        )
        update_counts(
            create_auctions(
                count=20,
                bid_asset_id=AssetId(60),
                min_bid=200,
                auction_app_id_start_at=71,
            )
        )
        update_counts(
            create_auctions(
                count=30,
                bid_asset_id=AssetId(60),
                min_bid=300,
                auction_app_id_start_at=91,
            )
        )

        logger.info(auctions_by_bid_asset_min_bid)

        search_request = AuctionSearchRequest(filters=AuctionSearchFilters(min_bid=100))
        search_result = self.search_auction(search_request)
        for auction in search_result.auctions:
            self.assertGreaterEqual(auction.state.min_bid, 100)
        expected_count = sum(
            [
                count
                for (
                bid_asset_id,
                min_bid,
            ), count in auctions_by_bid_asset_min_bid.items()
                if min_bid >= 100
            ]
        )
        self.assertEqual(expected_count, search_result.total_count)

        search_request = AuctionSearchRequest(filters=AuctionSearchFilters(min_bid=200))
        search_result = self.search_auction(search_request)
        for auction in search_result.auctions:
            self.assertGreaterEqual(auction.state.min_bid, 200)
        expected_count = sum(
            [
                count
                for (
                bid_asset_id,
                min_bid,
            ), count in auctions_by_bid_asset_min_bid.items()
                if min_bid >= 200
            ]
        )
        self.assertEqual(expected_count, search_result.total_count)

        search_request = AuctionSearchRequest(filters=AuctionSearchFilters(min_bid=300))
        search_result = self.search_auction(search_request)
        for auction in search_result.auctions:
            self.assertGreaterEqual(auction.state.min_bid, 300)
        expected_count = sum(
            [
                count
                for (
                bid_asset_id,
                min_bid,
            ), count in auctions_by_bid_asset_min_bid.items()
                if min_bid >= 300
            ]
        )
        self.assertEqual(expected_count, search_result.total_count)

        # filter on both min_bid and bid_asset_id
        search_request = AuctionSearchRequest(
            filters=AuctionSearchFilters(
                min_bid=100,
                bid_asset_id={AssetId(50)},
            )
        )
        search_result = self.search_auction(search_request)
        for auction in search_result.auctions:
            self.assertGreaterEqual(auction.state.min_bid, 100)
            self.assertEqual(AssetId(50), auction.state.bid_asset_id)
        expected_count = sum(
            [
                count
                for (
                bid_asset_id,
                min_bid,
            ), count in auctions_by_bid_asset_min_bid.items()
                if min_bid >= 100 and bid_asset_id == AssetId(50)
            ]
        )
        self.assertEqual(expected_count, search_result.total_count)


if __name__ == "__main__":
    unittest.main()
