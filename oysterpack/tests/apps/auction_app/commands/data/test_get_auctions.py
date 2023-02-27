import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction_app.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction_app.commands.data.queries.get_auction import GetAuction
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.data import Base
from tests.apps.auction_app.commands.data import create_auctions
from tests.apps.auction_app.commands.data import register_auction_manager


class GetAuctionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.get_auction = GetAuction(self.session_factory)
        self.delete_auctions = DeleteAuctions(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_get_auction(self):
        auctions = create_auctions()
        register_auction_manager(
            self.session_factory, auctions[0].auction_manager_app_id
        )
        result = self.store_auctions(auctions)
        self.assertEqual(len(auctions), result.inserts)
        self.assertEqual(0, result.updates)

        for auction in auctions:
            self.assertEqual(auction, self.get_auction(auction.app_id))

        self.delete_auctions([auction.app_id for auction in auctions])

        for auction in auctions:
            self.assertIsNone(self.get_auction(auction.app_id))


if __name__ == "__main__":
    unittest.main()
