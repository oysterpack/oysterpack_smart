import unittest
from pprint import pp

from beaker import sandbox

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.data.auction_indexer_client import AuctionIndexerClient
from tests.algorand.test_support import AlgorandTestCase


class AuctionIndexerClientTestCase(AlgorandTestCase):
    def test_search_auctions(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        auction_indexer_client = AuctionIndexerClient(
            indexer_client=self.indexer,
            algod_client=self.algod_client,
            auction_manager_app_id=creator_app_client.app_id,
        )

        with self.subTest(
            "create AuctionIndexerClient with an invalid AuctionManager app ID"
        ):
            AuctionIndexerClient(
                indexer_client=self.indexer,
                algod_client=self.algod_client,
                auction_manager_app_id=creator_app_client.app_id,
            )

        with self.subTest("no auctions have been created"):
            auctions = auction_indexer_client.search_auctions()
            pp(auctions)

        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )
        for _ in range(10):
            seller_auction_manager_client.create_auction()

        with self.subTest("retrieve all auctions"):
            search_result = auction_indexer_client.search_auctions()
            self.assertEqual(len(search_result.auctions), 10)
            search_result = auction_indexer_client.search_auctions(
                next_page=search_result.next_page
            )
            self.assertEqual(len(search_result.auctions), 0)


if __name__ == "__main__":
    unittest.main()
