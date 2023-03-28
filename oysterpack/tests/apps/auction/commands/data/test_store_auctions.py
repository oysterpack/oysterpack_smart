import unittest

from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction.commands.data.queries.get_auction import GetAuction
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.data.auction import TAuction, TAuctionAsset
from oysterpack.apps.auction.domain.auction import Auction
from tests.apps.auction.commands.data import create_auctions
from tests.apps.auction.commands.data import register_auction_manager


class StoreAuctionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.get_auction = GetAuction(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_insert_new_records(self):
        # pylint: disable=not-callable
        # pylint: disable=too-many-function-args

        auctions = create_auctions()
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        result = self.store_auctions(auctions)
        self.assertEqual(len(auctions), result.inserts)
        self.assertEqual(0, result.updates)

        for auction in auctions:
            self.assertEqual(auction, self.get_auction(auction.app_id))

        with self.session_factory() as session:
            query = select(func.count(TAuction.app_id))
            count = session.scalar(query)
            self.assertEqual(len(auctions), count)

            for auction in auctions:
                stored_auction: TAuction | None = session.get(TAuction, auction.app_id)  # type: ignore
                self.assertIsNotNone(stored_auction)
                self.assertEqual(auction, stored_auction.to_auction())

            # load the TAuction records manually from the database
            # this effectively checks the database schema against the mapped entities
            for row in session.execute(text("select * from auction")):
                tauction = TAuction(
                    row.app_id,
                    row.auction_manager_app_id,
                    row.updated_at,
                    [],
                )
                tauction.status = row.status
                tauction.seller = row.seller
                tauction.bid_asset_id = row.bid_asset_id
                tauction.min_bid = row.min_bid
                tauction.highest_bidder = row.highest_bidder
                tauction.highest_bid = row.highest_bid
                tauction.start_time = row.start_time
                tauction.end_time = row.end_time

                for row in session.execute(
                    text(
                        f"select * from auction_asset where auction_id={tauction.app_id}"
                    )
                ):
                    tauction.assets.append(
                        TAuctionAsset(
                            row.auction_id,
                            row.asset_id,
                            row.amount,
                        )
                    )

                self.assertTrue(tauction.to_auction() in auctions)

    def test_update(self):
        # pylint: disable=not-callable

        # insert auctions
        auctions = create_auctions()
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        result = self.store_auctions(auctions)
        self.assertEqual(len(auctions), result.inserts)
        self.assertEqual(0, result.updates)

        # try to insert them again
        result = self.store_auctions(auctions)
        self.assertEqual(0, result.inserts)
        self.assertEqual(len(auctions), result.updates)

        with self.session_factory() as session:
            self.assertEqual(len(auctions), session.scalar(func.count(TAuction.app_id)))

        # update the auctions by incrementing the auction app IDs by one
        # also increment auction asset amounts
        for auction in auctions:
            auction.app_id += 1
            for asset_id, amount in auction.assets.items():
                auction.assets[asset_id] = amount + 10
        result = self.store_auctions(auctions)

        self.assertEqual(1, result.inserts)
        self.assertEqual(len(auctions) - 1, result.updates)

        with self.session_factory() as session:
            self.assertEqual(
                len(auctions) + 1, session.scalar(func.count(TAuction.app_id))
            )

            # check that the auction asset records were inserted for the new auction
            expected_auction_asset_count = 0
            for auction in auctions:
                expected_auction_asset_count += len(auction.assets)
            expected_auction_asset_count += len(auctions[-1].assets)

            self.assertEqual(
                expected_auction_asset_count,
                session.scalar(func.count(TAuctionAsset.auction_id)),
            )

            for tauction in session.scalars(select(TAuction)):
                stored_auction: Auction = tauction.to_auction()  # type: ignore
                if stored_auction.app_id == 1:
                    continue
                self.assertTrue(stored_auction in auctions, f"{stored_auction}")

    def test_searching_and_paging_auctions(self):
        auctions = create_auctions()
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        self.store_auctions(auctions)

        page_size = 10
        # get first page
        with self.session_factory() as session:
            auctions_search_result = [
                auction.to_auction()
                for auction in session.scalars(
                    select(TAuction).limit(page_size).order_by(TAuction.app_id)
                )
            ]
            self.assertEqual(page_size, len(auctions_search_result))
            # get next page
            max_app_id = auctions_search_result[-1].app_id
            auctions_search_result = [
                auction.to_auction()
                for auction in session.scalars(
                    select(TAuction)
                    .order_by(TAuction.app_id)
                    .limit(page_size)
                    .offset(page_size)
                )
            ]
            self.assertEqual(page_size, len(auctions_search_result))
            self.assertEqual(max_app_id + 1, auctions_search_result[0].app_id)


if __name__ == "__main__":
    unittest.main()
