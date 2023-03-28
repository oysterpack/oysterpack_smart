import unittest
from datetime import datetime, UTC, timedelta
from typing import Tuple, cast

from algosdk.account import generate_account
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address, AssetId
from oysterpack.apps.auction.commands.data.queries.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
    AuctionSort,
    AuctionSortField,
    AuctionSearchFilters,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.domain.auction import Auction
from tests.apps.auction.commands.data import create_auctions
from tests.apps.auction.commands.data import register_auction_manager
from tests.test_support import OysterPackTestCase


class SearchAuctionsTestCase(OysterPackTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.search_auctions = SearchAuctions(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_search_with_no_filters_no_sorts(self):
        logger = super().get_logger("test_search_with_no_filters_no_sorts")
        auction_count = 101
        auctions = create_auctions(auction_count)
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        # page through auctions
        search_request = AuctionSearchRequest(limit=10)
        search_result = self.search_auctions(search_request)
        logger.info(
            f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
        )
        self.assertEqual(auction_count, search_result.total_count)
        self.assertEqual(search_request.limit, len(search_result.auctions))
        auctions_retrieved_from_search = search_result.auctions

        while search_request := search_request.next_page(search_result):
            logger.info(f"search_request: {search_request}")
            search_result = self.search_auctions(search_request)
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
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        search_request = AuctionSearchRequest(limit=10, offset=auction_count - 1)
        search_result = self.search_auctions(search_request)
        logger.info(
            f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
        )
        auctions_retrieved_from_search = search_result.auctions
        while search_request := search_request.previous_page(search_result):
            logger.info(f"search_request: {search_request}")
            search_result = self.search_auctions(search_request)
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
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        search_request = AuctionSearchRequest(limit=10, offset=auction_count - 1)
        search_result = self.search_auctions(search_request)

        search_request = search_request.goto(search_result, offset=50)
        search_result = self.search_auctions(search_request)
        self.assertEqual(51, search_result.auctions[0].app_id)
        self.assertEqual(60, search_result.auctions[-1].app_id)

        search_request = search_request.goto(search_result, offset=0)
        search_result = self.search_auctions(search_request)
        self.assertEqual(1, search_result.auctions[0].app_id)
        self.assertEqual(10, search_result.auctions[-1].app_id)

        search_request = search_request.goto(search_result, offset=95)
        search_result = self.search_auctions(search_request)
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
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        # page through auctions
        search_request = AuctionSearchRequest(
            limit=10,
            sort=AuctionSort(
                field=AuctionSortField.AUCTION_ID,
                asc=False,
            ),
        )
        search_result = self.search_auctions(search_request)
        logger.info(
            f"search result auction app IDS: {[auction.app_id for auction in search_result.auctions]}"
        )
        self.assertEqual(auction_count, search_result.total_count)
        self.assertEqual(search_request.limit, len(search_result.auctions))
        auctions_retrieved_from_search = search_result.auctions

        while search_request := search_request.next_page(search_result):
            search_result = self.search_auctions(search_request)
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
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        auction_ids = [auction.app_id for auction in auctions]

        with self.subTest("single Auction ID filter"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(app_id=set(auction_ids[0:1])),
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(1, search_result.total_count)
            self.assertEqual(auctions[0], search_result.auctions[0])

        with self.subTest("multiple Auction ID filter"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(app_id=set(auction_ids[0:5])),
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(5, search_result.total_count)
            self.assertEqual(auctions[0:5], search_result.auctions)

        with self.subTest("single status filter"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(status={AuctionStatus.NEW}),
            )
            search_result = self.search_auctions(search_request)
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
            search_result = self.search_auctions(search_request)
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
            auctions = create_auctions(5, seller=Address(seller_1))
            register_auction_manager(
                self.session_factory, auctions[0].auction_manager_app_id
            )
            self.store_auctions(auctions)

            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(seller={seller_1}),
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(5, search_result.total_count)
            for auction in search_result.auctions:
                self.assertEqual(seller_1, auction.state.seller)

        with self.subTest("multiple seller filter"):
            _private_key, seller_2 = generate_account()
            auctions = create_auctions(10, seller=Address(seller_1))
            register_auction_manager(
                self.session_factory, auctions[0].auction_manager_app_id
            )
            self.store_auctions(auctions)
            # updates the first 5 to seller_2
            auctions = create_auctions(5, seller=Address(seller_2))
            self.store_auctions(auctions)

            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(seller={seller_1, seller_2}),
            )
            search_result = self.search_auctions(search_request)
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
            register_auction_manager(
                self.session_factory, auctions[0].auction_manager_app_id
            )
            self.store_auctions(auctions)
            auction_app_id_start_at += bid_asset_id

        logger.info(bid_asset_ids)

        with self.subTest("single value search"):
            for bid_asset_id in bid_asset_ids:
                search_request = AuctionSearchRequest(
                    filters=AuctionSearchFilters(bid_asset_id={bid_asset_id}),
                )
                search_result = self.search_auctions(search_request)
                self.assertEqual(bid_asset_ids[bid_asset_id], search_result.total_count)

        with self.subTest("multi-value search"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(bid_asset_id={AssetId(50), AssetId(60)}),
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(
                bid_asset_ids[AssetId(50)] + bid_asset_ids[AssetId(60)],
                search_result.total_count,
            )

    def test_min_bid_filter(self):
        logger = super().get_logger("test_min_bid_filter")
        # SETUP
        # create auctions with different bid assets and min bids

        auctions_by_bid_asset_min_bid: dict[Tuple[AssetId, int], int] = {}  # type: ignore

        def create_auctions_and_track_counts(
            count: int,
            bid_asset_id: AssetId,
            min_bid: int,
            auction_app_id_start_at: int,
        ):
            def update_counts(auctions: list[Auction]):
                register_auction_manager(
                    self.session_factory, auctions[0].auction_manager_app_id
                )
                result = self.store_auctions(auctions)
                logger.info(result)
                for auction in auctions:
                    if auction.state.bid_asset_id is not None:
                        key = (
                            auction.state.bid_asset_id,
                            cast(int, auction.state.min_bid),
                        )
                        if key in auctions_by_bid_asset_min_bid:
                            auctions_by_bid_asset_min_bid[key] += 1
                        else:
                            auctions_by_bid_asset_min_bid[key] = 1

            update_counts(
                create_auctions(
                    count=count,
                    bid_asset_id=bid_asset_id,
                    min_bid=min_bid,
                    auction_app_id_start_at=auction_app_id_start_at,
                )
            )

        create_auctions_and_track_counts(
            count=10,
            bid_asset_id=AssetId(50),
            min_bid=100,
            auction_app_id_start_at=1,
        )
        create_auctions_and_track_counts(
            count=20,
            bid_asset_id=AssetId(50),
            min_bid=200,
            auction_app_id_start_at=11,
        )
        create_auctions_and_track_counts(
            count=30,
            bid_asset_id=AssetId(50),
            min_bid=300,
            auction_app_id_start_at=31,
        )

        create_auctions_and_track_counts(
            count=10,
            bid_asset_id=AssetId(60),
            min_bid=100,
            auction_app_id_start_at=61,
        )
        create_auctions_and_track_counts(
            count=20,
            bid_asset_id=AssetId(60),
            min_bid=200,
            auction_app_id_start_at=71,
        )
        create_auctions_and_track_counts(
            count=30,
            bid_asset_id=AssetId(60),
            min_bid=300,
            auction_app_id_start_at=91,
        )

        logger.info(auctions_by_bid_asset_min_bid)

        # ACT
        for min_bid_filter in [100, 200, 300]:
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(min_bid=min_bid_filter)
            )
            search_result = self.search_auctions(search_request)
            for auction in search_result.auctions:
                self.assertGreaterEqual(auction.state.min_bid, min_bid_filter)
            expected_count = sum(
                [
                    count
                    for (
                        bid_asset_id,
                        min_bid,
                    ), count in auctions_by_bid_asset_min_bid.items()
                    if min_bid >= min_bid_filter
                ]
            )
            self.assertEqual(
                expected_count, search_result.total_count, f"min_bid = {min_bid_filter}"
            )

        with self.subTest("filter on both min_bid and bid_asset_id"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    min_bid=100,
                    bid_asset_id={AssetId(50)},
                )
            )
            search_result = self.search_auctions(search_request)
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

    def test_highest_bidder_filter(self):
        _private_key_1, highest_bidder_1 = generate_account()
        auctions = create_auctions(
            count=10,
            highest_bidder=Address(highest_bidder_1),
            auction_app_id_start_at=1,
        )

        _private_key_2, highest_bidder_2 = generate_account()
        auctions += create_auctions(
            count=20,
            highest_bidder=Address(highest_bidder_2),
            auction_app_id_start_at=11,
        )

        _private_key_3, highest_bidder_3 = generate_account()
        auctions += create_auctions(
            count=20,
            highest_bidder=Address(highest_bidder_3),
            auction_app_id_start_at=31,
        )
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        with self.subTest("single value search"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(highest_bidder={Address(highest_bidder_1)})
            )
            search_result = self.search_auctions(search_request)
            for auction in search_result.auctions:
                self.assertEqual(
                    Address(highest_bidder_1), auction.state.highest_bidder
                )
            expected_count = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.highest_bidder == Address(highest_bidder_1)
                ]
            )
            self.assertEqual(expected_count, search_result.total_count)

        with self.subTest("multi-value search"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    highest_bidder={
                        Address(highest_bidder_1),
                        Address(highest_bidder_3),
                    }
                )
            )
            search_result = self.search_auctions(search_request)
            for auction in search_result.auctions:
                self.assertIn(
                    auction.state.highest_bidder,
                    {Address(highest_bidder_1), Address(highest_bidder_3)},
                )
            expected_count = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.highest_bidder
                    in {Address(highest_bidder_1), Address(highest_bidder_3)}
                ]
            )
            self.assertEqual(expected_count, search_result.total_count)

    def test_highest_bid_filter(self):
        auctions = create_auctions(
            count=10,
            highest_bid=1000,
            auction_app_id_start_at=1,
        )
        auctions += create_auctions(
            count=20,
            highest_bid=2000,
            auction_app_id_start_at=11,
        )
        auctions += create_auctions(
            count=30,
            highest_bid=3000,
            auction_app_id_start_at=31,
        )
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        for highest_bid in [1000, 2000, 3000]:
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(highest_bid=highest_bid)
            )
            search_result = self.search_auctions(search_request)
            for auction in search_result.auctions:
                self.assertGreaterEqual(
                    auction.state.highest_bid, search_request.filters.highest_bid
                )
            expected_count = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.highest_bid
                    and auction.state.highest_bid >= search_request.filters.highest_bid
                ]
            )
            self.assertEqual(
                expected_count, search_result.total_count, f"highest_bid={highest_bid}"
            )

    def test_start_time_filter(self):
        now = datetime.fromtimestamp(int(datetime.now(UTC).timestamp()), UTC)
        auctions = create_auctions(count=10, start_time=now, auction_app_id_start_at=1)
        start_time = now + timedelta(days=1)
        auctions += create_auctions(
            count=20, start_time=start_time, auction_app_id_start_at=11
        )
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        for start_time_filter in [now, now + timedelta(hours=1), start_time]:
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(start_time=start_time_filter)
            )
            search_result = self.search_auctions(search_request)
            expected_count = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.start_time
                    and auction.state.start_time >= search_request.filters.start_time
                ]
            )
            self.assertEqual(expected_count, search_result.total_count)

    def test_end_time_filter(self):
        now = datetime.fromtimestamp(int(datetime.now(UTC).timestamp()), UTC)
        end_time_1 = now + timedelta(days=1)
        auctions = create_auctions(
            count=10, end_time=end_time_1, auction_app_id_start_at=1
        )
        end_time_2 = end_time_1 + timedelta(days=1)
        auctions += create_auctions(
            count=20, end_time=end_time_2, auction_app_id_start_at=11
        )
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        for end_time_filter in [
            end_time_1,
            end_time_1 - timedelta(hours=1),
            end_time_2,
        ]:
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(end_time=end_time_filter)
            )
            search_result = self.search_auctions(search_request)
            expected_count = len(
                [
                    auction
                    for auction in auctions
                    if auction.state.start_time
                    and auction.state.end_time <= search_request.filters.end_time
                ]
            )
            self.assertEqual(expected_count, search_result.total_count)

    def test_assets_filter(self):
        auctions = create_auctions(
            assets={AssetId(100): 100, AssetId(200): 200},
            count=10,
            auction_app_id_start_at=1,
        )
        auctions += create_auctions(
            assets={AssetId(300): 300, AssetId(200): 250},
            count=20,
            auction_app_id_start_at=11,
        )
        auctions += create_auctions(
            assets={AssetId(300): 350, AssetId(400): 400},
            count=30,
            auction_app_id_start_at=31,
        )
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        with self.subTest("single asset search"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(assets={AssetId(200)})
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(30, search_result.total_count)
            for auction in search_result.auctions:
                self.assertIn(AssetId(200), auction.assets)

        with self.subTest("multi-asset search"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(assets={AssetId(100), AssetId(400)})
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(40, search_result.total_count)
            for auction in search_result.auctions:
                self.assertTrue(
                    AssetId(100) in auction.assets or AssetId(400) in auction.assets
                )

        with self.subTest("single asset amount search"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(asset_amounts={AssetId(200): 210})
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(20, search_result.total_count)
            for auction in search_result.auctions:
                self.assertGreaterEqual(auction.assets[AssetId(200)], 210)

        with self.subTest("multi-asset amount search"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    asset_amounts={AssetId(200): 210, AssetId(300): 310}
                )
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(50, search_result.total_count)
            for auction in search_result.auctions:
                self.assertTrue(
                    (
                        AssetId(200) in auction.assets
                        and auction.assets[AssetId(200)] >= 210
                    )
                    or (
                        AssetId(300) in auction.assets
                        and auction.assets[AssetId(300)] >= 310
                    )
                )

        with self.subTest("assets overlapping with asset_amounts"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    assets={AssetId(200)},
                    asset_amounts={AssetId(200): 210, AssetId(300): 310},
                )
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(50, search_result.total_count)
            for auction in search_result.auctions:
                self.assertTrue(
                    (
                        AssetId(200) in auction.assets
                        and auction.assets[AssetId(200)] >= 210
                    )
                    or (
                        AssetId(300) in auction.assets
                        and auction.assets[AssetId(300)] >= 310
                    )
                )

        with self.subTest("assets non-overlapping with asset_amounts"):
            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    assets={AssetId(100)}, asset_amounts={AssetId(200): 210}
                )
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(30, search_result.total_count)
            for auction in search_result.auctions:
                self.assertTrue(
                    AssetId(100) in auction.assets
                    or (
                        AssetId(200) in auction.assets
                        and auction.assets[AssetId(200)] >= 210
                    )
                )

            search_request = AuctionSearchRequest(
                filters=AuctionSearchFilters(
                    assets={AssetId(100)},
                    asset_amounts={AssetId(200): 210, AssetId(300): 310},
                )
            )
            search_result = self.search_auctions(search_request)
            self.assertEqual(60, search_result.total_count)
            for auction in search_result.auctions:
                self.assertTrue(
                    AssetId(100) in auction.assets
                    or (
                        AssetId(200) in auction.assets
                        and auction.assets[AssetId(200)] >= 210
                    )
                    or (
                        AssetId(300) in auction.assets
                        and auction.assets[AssetId(300)] >= 310
                    )
                )


if __name__ == "__main__":
    unittest.main()
