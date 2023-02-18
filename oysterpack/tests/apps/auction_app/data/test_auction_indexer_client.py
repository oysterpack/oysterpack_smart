import unittest
from time import sleep

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
            self.assertEqual(len(auctions.auctions), 0)

        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )

        with self.subTest("create auctions and then retrieve them via search"):
            for _ in range(3):
                seller_auction_manager_client.create_auction()
            sleep(1)

            search_result = auction_indexer_client.search_auctions(limit=2)
            self.assertEqual(len(search_result.auctions), 2)

            count = 2
            while True:
                search_result = auction_indexer_client.search_auctions(
                    limit=1, next_token=search_result.next_page
                )
                if len(search_result.auctions) == 0:
                    break
                count += 1
                self.assertFalse(count > 3)

            self.assertEqual(count, 3)

    def test_search_auction_paging(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )

        auction_indexer_client = AuctionIndexerClient(
            indexer_client=self.indexer,
            algod_client=self.algod_client,
            auction_manager_app_id=creator_app_client.app_id,
        )

        app_ids = []
        for _ in range(5):
            app_ids.append(seller_auction_manager_client.create_auction().app_id)
        sleep(1)

        search_result = auction_indexer_client.search_auctions()
        self.assertEqual(len(search_result.auctions), 5)

        with self.subTest("retrieve Auctions that were created after an app ID"):
            search_result = auction_indexer_client.search_auctions(
                next_token=app_ids[2]
            )
            self.assertEqual(len(search_result.auctions), 2)

        with self.subTest("retrieve Auction that were created since the last search"):
            for _ in range(3):
                app_ids.append(seller_auction_manager_client.create_auction().app_id)
            sleep(1)

            search_result = auction_indexer_client.search_auctions(
                next_token=app_ids[4]
            )
            self.assertEqual(len(search_result.auctions), 3)
            for auction in search_result.auctions:
                self.assertIsNotNone(auction.app_id, app_ids)


if __name__ == "__main__":
    unittest.main()
