import unittest
from time import sleep

from beaker import sandbox

from oysterpack.algorand.client.model import Address, AppId
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_manager_events import (
    SearchAuctionManagerEvents,
    SearchAuctionManagerEventsRequest,
    AuctionManagerEvent,
)
from tests.algorand.test_support import AlgorandTestCase


class SearchAuctionManagerEventsTestCase(AlgorandTestCase):
    def test_search_auction_manager_events(self):
        logger = super().get_logger("test_search_auction_events")
        search_auction_events = SearchAuctionManagerEvents(self.indexer)

        def search_events(
            event: AuctionManagerEvent, auction_client_app_ids: list[AppId] | None
        ):
            request = SearchAuctionManagerEventsRequest(
                auction_manager_app_id=creator_app_client.app_id,
                event=event,
            )
            result = search_auction_events(request)
            logger.info(result)
            self.assertEqual(event, result.event)
            if auction_client_app_ids is None:
                self.assertIsNone(result.auctions)
            else:
                self.assertEqual(len(auction_client_app_ids), len(result.auctions))
                for app_id in auction_client_app_ids:
                    self.assertIn(app_id, result.auctions)

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

        search_events(AuctionManagerEvent.AUCTION_CREATED, None)
        search_events(AuctionManagerEvent.AUCTION_DELETED, None)

        auction_clients = []
        for _ in range(2):
            auction_client = seller_auction_manager_client.create_auction()
            auction_client.cancel()
            auction_client.finalize()
            auction_clients.append(auction_client)
        sleep(1)
        auction_client_app_ids = [
            auction_client.app_id for auction_client in auction_clients
        ]

        search_events(AuctionManagerEvent.AUCTION_CREATED, auction_client_app_ids)
        search_events(AuctionManagerEvent.AUCTION_DELETED, None)

        for auction_client in auction_clients:
            creator_app_client.delete_finalized_auction(auction_client.app_id)
        sleep(1)

        search_events(AuctionManagerEvent.AUCTION_CREATED, auction_client_app_ids)
        search_events(AuctionManagerEvent.AUCTION_DELETED, auction_client_app_ids)


if __name__ == "__main__":
    unittest.main()
