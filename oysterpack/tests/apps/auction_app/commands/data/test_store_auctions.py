import unittest
from datetime import datetime, UTC, timedelta

from algosdk.account import generate_account
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.data.auction import TAuction, TAuctionAsset
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState


class MyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def create_auctions(self, count: int = 100):
        _private_key, creator = generate_account()
        _private_key, seller = generate_account()
        _private_key, bidder = generate_account()

        states = [
            AuctionState(
                status=AuctionStatus.NEW,
                seller=Address(seller),
            ),
            AuctionState(
                status=AuctionStatus.COMMITTED,
                seller=Address(seller),
                bid_asset_id=AssetId(10),
                min_bid=100,
                highest_bidder=None,
                highest_bid=0,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC) + timedelta(days=1),
            ),
            AuctionState(
                status=AuctionStatus.BID_ACCEPTED,
                seller=Address(seller),
                bid_asset_id=AssetId(10),
                min_bid=100,
                highest_bidder=Address(bidder),
                highest_bid=1000,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC) + timedelta(days=1),
            ),
            AuctionState(
                status=AuctionStatus.FINALIZED,
                seller=Address(seller),
                bid_asset_id=AssetId(10),
                min_bid=100,
                highest_bidder=Address(bidder),
                highest_bid=1000,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC) + timedelta(days=1),
            ),
            AuctionState(
                status=AuctionStatus.CANCELLED,
                seller=Address(seller),
            ),
        ]

        return [
            Auction(
                app_id=AppId(i),
                creator=Address(creator),
                created_at_round=i + 1,
                round=i + 2,
                state=states[i % 5],
                assets={
                    AssetId(i): i,
                    AssetId(i + 1): i + 1,
                    AssetId(i + 2): i + 2,
                },
            )
            for i in range(1, count + 1)
        ]

    def test_insert_new_records(self):
        auctions = self.create_auctions()
        result = self.store_auctions(auctions)
        self.assertEqual(len(auctions), result.inserts)
        self.assertEqual(0, result.updates)

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
                    row.creator,
                    row.created_at_round,
                    row.updated_at,
                    row.updated_at_round,
                    []
                )
                tauction.status = row.status
                tauction.seller = row.seller
                tauction.bid_asset_id = row.bid_asset_id
                tauction.min_bid = row.min_bid
                tauction.highest_bidder = row.highest_bidder
                tauction.highest_bid = row.highest_bid
                tauction.start_time = row.start_time
                tauction.end_time = row.end_time

                for row in session.execute(text(f"select * from auction_asset where auction_id={tauction.app_id}")):
                    tauction.assets.append(
                        TAuctionAsset(
                            row.auction_id,
                            row.asset_id,
                            row.amount,
                        )
                    )

                self.assertTrue(tauction.to_auction() in auctions)

    def test_update(self):
        # insert auctions
        auctions = self.create_auctions()
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
            self.assertEqual(len(auctions) + 1, session.scalar(func.count(TAuction.app_id)))

            # check that the auction asset records were inserted for the new auction
            expected_auction_asset_count = 0
            for auction in auctions:
                expected_auction_asset_count += len(auction.assets)
            expected_auction_asset_count += len(auctions[-1].assets)

            self.assertEqual(expected_auction_asset_count, session.scalar(func.count(TAuctionAsset.auction_id)))

            for tauction in session.scalars(select(TAuction)):
                stored_auction: Auction = tauction.to_auction()  # type: ignore
                if (stored_auction.app_id == 1): continue
                self.assertTrue(stored_auction in auctions, f"{stored_auction}")


if __name__ == "__main__":
    unittest.main()
