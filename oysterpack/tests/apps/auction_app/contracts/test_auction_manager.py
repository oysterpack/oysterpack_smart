import unittest

from beaker import sandbox

from oysterpack.apps.auction_app.client.auction_manager_client import (
    AuctionManagerClient,
    create_auction_manager,
)
from oysterpack.apps.auction_app.contracts.auction_manager import AuctionManager
from tests.algorand.test_support import AlgorandTestSupport


class AuctionFactoryTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_create(self):
        logger = super().get_logger("test_create")
        # SETUP
        app_client = self.sandbox_application_client(AuctionManager())
        app_client.build()

        # ACT
        app_client.create()
        auction_manager_client = AuctionManagerClient.from_client(app_client)
        logger.info(
            f"auction creation fees = {auction_manager_client.get_auction_creation_fees()} microalgos"
        )

    def test_create_auction(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        seller_app_client = creator_app_client.prepare(signer=seller.signer)

        # ACT
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller_address)

        # create another auction
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller_address)


if __name__ == "__main__":
    unittest.main()
