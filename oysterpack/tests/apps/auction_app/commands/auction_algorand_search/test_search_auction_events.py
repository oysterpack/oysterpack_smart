import unittest
from datetime import datetime, UTC, timedelta
from time import sleep

from beaker import sandbox

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_events import (
    SearchAuctionEvents,
    SearchAuctionEventsRequest,
    AuctionEvent,
)
from tests.algorand.test_support import AlgorandTestCase


class MyTestCase(AlgorandTestCase):
    def test_search_auction_events(self):
        logger = super().get_logger("test_search_auction_events")
        search_auction_events = SearchAuctionEvents(self.indexer)

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

        auction_clients = []
        for _ in range(5):
            auction_clients.append(seller_auction_manager_client.create_auction())
        sleep(1)

        gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
        bid_asset_id, bid_asset_manager_address = self.create_test_asset("USD$")

        # opt in assets for the seller account
        starting_asset_balance = 1_000_000
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=gold_asset_manager_address,
        )
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )

        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(days=3)
        for auction_client in auction_clients:
            auction_client.set_bid_asset(bid_asset_id, 10_000)
            auction_client.optin_asset(gold_asset_id)
            auction_client.deposit_asset(gold_asset_id, 10_000)
            auction_client.commit(start_time, end_time)

        sleep(1)

        for auction_client in auction_clients:
            request = SearchAuctionEventsRequest(
                auction_app_id=auction_client.app_id, event=AuctionEvent.COMMITTED
            )
            result = search_auction_events(request)
            logger.info(result)
            self.assertEqual(AuctionEvent.COMMITTED, result.event)
            self.assertEqual(1, len(result.txn_ids))


if __name__ == "__main__":
    unittest.main()
