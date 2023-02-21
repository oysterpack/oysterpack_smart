import unittest
from typing import cast

from algosdk.account import generate_account
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session, Mapped

from oysterpack.algorand.client.model import AssetId, Address, AppId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data.asset_info import TAssetInfo
from oysterpack.apps.auction_app.data.auction import Base, TAuction, TAuctionAsset
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState
from tests.algorand.test_support import AlgorandTestCase


class MyTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=True)
        Base.metadata.create_all(self.engine)

    def test_crud(self):
        # pylint is complaining about func.count() constructs, which are valid
        # pylint: disable=not-callable

        _, creator = generate_account()
        _, seller = generate_account()

        # create
        with Session(self.engine) as session:
            for i in range(1, 101):
                if session.get(TAssetInfo, i) is None:
                    session.add(
                        TAssetInfo(
                            asset_id=cast(Mapped[int], i),
                            creator=cast(Mapped[Address], creator),
                            total=cast(Mapped[int], 1_000_000_000_000_000),
                            decimals=cast(Mapped[int], 6),
                        )
                    )

            for i in range(1, 11):
                auction = Auction(
                    app_id=AppId(1 + i),
                    creator=Address(creator),
                    created_at_round=2 + i,
                    state=AuctionState(
                        seller=Address(seller),
                        status=AuctionStatus.NEW,
                    ),
                    assets={
                        AssetId(4 + i): 1000 * i,
                        AssetId(5 + i): 2000 * i,
                    },
                    round=6 + i,
                )
                session.add(TAuction.create(auction))

            session.commit()

        # read
        with Session(self.engine) as session:
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
        with Session(self.engine) as session:
            auction = session.get(TAuction, 2)
            self.assertIsNotNone(auction)
            auction.set_assets(
                {
                    AssetId(15): 20,
                    AssetId(23): 34,
                }
            )
            session.commit()

        # delete
        with Session(self.engine) as session:
            auction = session.get(TAuction, 2)
            self.assertIsNotNone(auction)
            session.delete(auction)
            session.commit()

            auction = session.get(TAuction, 2)
            self.assertIsNone(auction)


if __name__ == "__main__":
    unittest.main()
