import unittest
from time import sleep

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
)
from tests.algorand.test_support import AlgorandTestCase


@unittest.skip(reason="beaker upgrade broke the contracts")
class SearchAuctionsTestCase(AlgorandTestCase):
    def test_search_auctions(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        search_auctions = SearchAuctions(
            indexer_client=self.indexer,
            algod_client=self.algod_client,
        )

        with self.subTest(
            "create AuctionIndexerClient with an invalid AuctionManager app ID"
        ):
            SearchAuctions(
                indexer_client=self.indexer,
                algod_client=self.algod_client,
            )

        with self.subTest("no auctions have been created"):
            search_result = search_auctions(
                AuctionSearchRequest(auction_manager_app_id=creator_app_client.app_id)
            )
            self.assertEqual(len(search_result.auctions), 0)

        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )

        with self.subTest("create auctions and then retrieve them via search"):
            for _ in range(5):
                seller_auction_manager_client.create_auction()
            sleep(1)  # give the indexer time to index

            search_result = search_auctions(
                AuctionSearchRequest(
                    auction_manager_app_id=creator_app_client.app_id,
                    limit=2,
                )
            )
            self.assertEqual(len(search_result.auctions), 2)

            count = 2
            while True:
                search_result = search_auctions(
                    AuctionSearchRequest(
                        auction_manager_app_id=creator_app_client.app_id,
                        limit=2,
                        next_token=search_result.next_token,
                    )
                )
                if len(search_result.auctions) == 0:
                    break
                count += len(search_result.auctions)
                self.assertFalse(count > 5)

            self.assertEqual(count, 5)

    def test_search_auction_paging(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )

        search_auctions = SearchAuctions(
            indexer_client=self.indexer,
            algod_client=self.algod_client,
        )

        app_ids = []
        for _ in range(5):
            app_ids.append(seller_auction_manager_client.create_auction().app_id)
        sleep(1)  # give the indexer time to index

        search_result = search_auctions(
            AuctionSearchRequest(auction_manager_app_id=creator_app_client.app_id)
        )
        self.assertEqual(len(search_result.auctions), 5)

        with self.subTest("retrieve Auctions that were created after an app ID"):
            search_result = search_auctions(
                AuctionSearchRequest(
                    auction_manager_app_id=creator_app_client.app_id,
                    next_token=app_ids[2],
                )
            )
            self.assertEqual(len(search_result.auctions), 2)

        with self.subTest("retrieve Auction that were created since the last search"):
            for _ in range(3):
                app_ids.append(seller_auction_manager_client.create_auction().app_id)
            sleep(1)  # give the indexer time to index

            search_result = search_auctions(
                AuctionSearchRequest(
                    auction_manager_app_id=creator_app_client.app_id,
                    next_token=app_ids[4],
                )
            )
            self.assertEqual(len(search_result.auctions), 3)
            for auction in search_result.auctions:
                self.assertIsNotNone(auction.app_id, app_ids)


if __name__ == "__main__":
    unittest.main()
