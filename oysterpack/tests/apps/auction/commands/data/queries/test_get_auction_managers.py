import unittest

from algosdk.logic import get_application_address
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
    RegisteredAuctionManager,
)
from oysterpack.apps.auction.commands.data.register_auction_manager import (
    RegisterAuctionManager,
)
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.domain.auction import AuctionManagerAppId


class GetRegisteredAuctionManagersTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_get_registered_managers(self):
        get_registered_auction_managers = GetRegisteredAuctionManagers(
            self.session_factory
        )
        with self.subTest("no AuctionManagers are registered"):
            self.assertEqual(0, len(get_registered_auction_managers()))

        with self.subTest("with registered AuctionManagers"):
            register_auction_manager = RegisterAuctionManager(self.session_factory)
            auction_manager_id = AuctionManagerAppId(100)
            register_auction_manager(auction_manager_id)
            auction_managers = get_registered_auction_managers()
            self.assertEqual(1, len(auction_managers))
            self.assertEqual(
                [
                    RegisteredAuctionManager(
                        auction_manager_id,
                        Address(get_application_address(auction_manager_id)),
                    )
                ],
                auction_managers,
            )


if __name__ == "__main__":
    unittest.main()
