import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction_app.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.data.auction import TAuctionManager
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from tests.test_support import OysterPackTestCase


class MyTestCase(OysterPackTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.lookup_auction_manager = LookupAuctionManager(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_lookup_auction_manager(self):
        auction_manager_app_id = AuctionManagerAppId(100)
        with self.subTest("using AppId that does not exist in the database"):
            self.assertIsNone(self.lookup_auction_manager(auction_manager_app_id))

        with self.subTest("auction manager exists in database"):
            # SETUP
            auction_manager = TAuctionManager.create(auction_manager_app_id)
            with self.session_factory.begin() as session:  # pylint: disable=no-member
                session.add(auction_manager)

            result = self.lookup_auction_manager(auction_manager_app_id)
            self.assertIsNotNone(result)

            self.assertEqual(
                TAuctionManager.create(auction_manager_app_id), TAuctionManager(*result)
            )


if __name__ == "__main__":
    unittest.main()
