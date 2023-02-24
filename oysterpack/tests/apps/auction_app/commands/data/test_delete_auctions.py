import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction_app.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.data.auction import TAuction, TAuctionAsset
from tests.apps.auction_app.commands.data import create_auctions


class DeleteAuctionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.delete_auctions = DeleteAuctions(self.session_factory)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_delete_records(self):
        # insert auctions
        auctions = create_auctions()
        result = self.store_auctions(auctions)
        self.assertEqual(len(auctions), result.inserts)
        self.assertEqual(0, result.updates)

        with self.session_factory() as session:
            self.assertEqual(len(auctions), session.scalar(select(func.count(TAuction.app_id))))

        app_ids = [auction.app_id for auction in auctions]
        self.delete_auctions(app_ids)

        with self.session_factory() as session:
            self.assertEqual(0, session.scalar(select(func.count(TAuction.app_id))))
            self.assertEqual(0, session.scalar(select(func.count(TAuctionAsset.auction_id))))

        # deleting again should be ok
        self.delete_auctions(app_ids)


if __name__ == "__main__":
    unittest.main()
