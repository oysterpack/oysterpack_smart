import unittest

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction.commands.data.register_auction_manager import (
    RegisterAuctionManager,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.commands.data.unregister_auction_manager import (
    UnregisterAuctionManager,
)
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.data.auction import TAuction
from oysterpack.apps.auction.domain.auction import AuctionManagerAppId
from tests.apps.auction.commands.data import create_auctions


class AuctionManagerRegistrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.register_auction_manager = RegisterAuctionManager(self.session_factory)
        self.unregister_auction_manager = UnregisterAuctionManager(self.session_factory)
        self.lookup_auction_manager = LookupAuctionManager(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_auction_manager_registration(self):
        # pylint: disable=not-callable

        auction_manager_app_id = AuctionManagerAppId(100)
        auctions = create_auctions(auction_manager_app_id=auction_manager_app_id)

        with self.subTest("register AuctionManager"):
            self.register_auction_manager(auction_manager_app_id)
            self.store_auctions(auctions)

            auction_manager_lookup_result = self.lookup_auction_manager(
                auction_manager_app_id
            )
            self.assertIsNotNone(auction_manager_lookup_result)
            self.assertEqual(auction_manager_app_id, auction_manager_lookup_result[0])

            with self.session_factory() as session:
                auction_count = session.scalar(select(func.count(TAuction.app_id)))
                self.assertEqual(len(auctions), auction_count)

        with self.subTest("unregister AuctionManager"):
            self.unregister_auction_manager(auction_manager_app_id)

            auction_manager_lookup_result = self.lookup_auction_manager(
                auction_manager_app_id
            )
            self.assertIsNone(auction_manager_lookup_result)

            with self.session_factory() as session:
                auction_count = session.scalar(select(func.count(TAuction.app_id)))
                self.assertEqual(0, auction_count)


if __name__ == "__main__":
    unittest.main()
