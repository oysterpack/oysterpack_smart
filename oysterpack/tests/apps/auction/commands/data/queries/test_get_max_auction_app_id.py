import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import AppId
from oysterpack.apps.auction.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
    AuctionManagerAppId,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.data import Base
from tests.apps.auction.commands.data import create_auctions
from tests.apps.auction.commands.data import register_auction_manager
from tests.test_support import OysterPackTestCase


class MyTestCase(OysterPackTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.get_max_auction_app_id = GetMaxAuctionAppId(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_empty_database(self):
        auctions = create_auctions(
            auction_manager_app_id=AppId(100),
            count=10,
        )
        auctions += create_auctions(
            auction_manager_app_id=AppId(200),
            count=20,
            auction_app_id_start_at=11,
        )
        register_auction_manager(self.session_factory, AppId(100))
        register_auction_manager(self.session_factory, AppId(200))
        self.store_auctions(auctions)

        self.assertIsNone(self.get_max_auction_app_id(AuctionManagerAppId(10)))
        self.assertEqual(10, self.get_max_auction_app_id(AuctionManagerAppId(100)))
        self.assertEqual(30, self.get_max_auction_app_id(AuctionManagerAppId(200)))


if __name__ == "__main__":
    unittest.main()
