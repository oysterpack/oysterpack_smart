import unittest
from typing import cast

from algosdk.account import generate_account
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import AssetId, Address, AppId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data.asset_info import TAssetInfo
from oysterpack.apps.auction_app.data.auction import Base, TAuction, TAuctionAsset
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState
from tests.algorand.test_support import AlgorandTestCase


class AuctionORMTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.Session = sessionmaker(self.engine)
        print(f"type(self.Session) = {type(self.Session)}")

        with self.Session() as session:
            result = session.scalars(text("PRAGMA foreign_keys")).one()
            self.assertEqual(1, result, "foreign keys should be enabled in SQLite")

    def tearDown(self) -> None:
        close_all_sessions()

    def test_crud(self):
        # pylint is complaining about func.count() constructs, which are valid
        # pylint: disable=not-callable

        _, creator = generate_account()
        _, seller = generate_account()

        # create
        with self.Session.begin() as session:  # pylint: disable=no-member
            for i in range(1, 101):
                with session.begin_nested():
                    session.add(
                        TAssetInfo(
                            asset_id=cast(Mapped[int], i),
                            creator=cast(Mapped[Address], creator),
                            total=cast(Mapped[int], 1_000_000_000_000_000),
                            decimals=cast(Mapped[int], 6),
                        )
                    )

                # sqlite supports savepoints
                # insert the asset_info records again using nested transaction
                # nested transactions should fail, but the outer transaction still continues
                try:
                    with session.begin_nested():
                        session.add(
                            TAssetInfo(
                                asset_id=cast(Mapped[int], i),
                                creator=cast(Mapped[Address], creator),
                                total=cast(Mapped[int], 1_000_000_000_000_000),
                                decimals=cast(Mapped[int], 6),
                            )
                        )
                except IntegrityError:
                    pass

            for i in range(1, 11):
                auction = Auction(
                    app_id=AppId(1 + i),
                    auction_manager_app_id=AppId(2 + i),
                    state=AuctionState(
                        seller=Address(seller),
                        status=AuctionStatus.NEW,
                    ),
                    assets={
                        AssetId(4 + i): 1000 * i,
                        AssetId(5 + i): 2000 * i,
                    },
                )
                session.add(TAuction.create(auction))

        # read
        with self.Session() as session:
            self.assertEqual(
                10,
                session.scalars(select(func.count(TAuction.app_id))).one(),
            )
            self.assertEqual(
                20,
                session.scalars(select(func.count(TAuctionAsset.asset_id))).one(),
            )
            self.assertEqual(
                100,
                session.scalars(select(func.count(TAssetInfo.asset_id))).one(),
            )

            query = (
                select(TAuction)
                .join(TAuction.assets)
                .where(TAuctionAsset.asset_id.in_([5, 10]))
            )
            for auction in session.scalars(query):
                print(auction.to_auction())

        # update
        with self.Session.begin() as session:  # pylint: disable=no-member
            auction = session.get(TAuction, 2)
            self.assertIsNotNone(auction)
            previous_auction_state = auction.to_auction()
            auction.set_assets(
                {
                    AssetId(15): 20,
                    AssetId(23): 34,
                }
            )

        with self.Session() as session:
            for asset_id, _amount in previous_auction_state.assets.items():
                query = (
                    select(TAuctionAsset)
                    .where(TAuctionAsset.auction_id == previous_auction_state.app_id)
                    .where(TAuctionAsset.asset_id == asset_id)
                )
                rs = session.scalar(query)
                self.assertIsNone(rs)

        # delete
        with self.Session.begin() as session:  # pylint: disable=no-member
            auction = session.get(TAuction, 2)
            self.assertIsNotNone(auction)
            session.delete(auction)

        with self.Session() as session:
            auction = session.get(TAuction, 2)
            self.assertIsNone(auction)


if __name__ == "__main__":
    unittest.main()
