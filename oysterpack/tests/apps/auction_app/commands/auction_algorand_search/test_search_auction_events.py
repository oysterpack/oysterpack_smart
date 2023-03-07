import pprint
import unittest
from datetime import datetime, UTC, timedelta
from time import sleep

from beaker import sandbox
from beaker.client import ApplicationClient

from oysterpack.algorand.client.model import Address
from oysterpack.algorand.client.transactions.note import AppTxnNote
from oysterpack.apps.auction_app.client.auction_client import (
    AuctionBidder,
    AuctionPhase,
    AuctionClient,
)
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_events import (
    SearchAuctionEvents,
    SearchAuctionEventsRequest,
    AuctionEvent,
)
from oysterpack.apps.auction_app.contracts.auction import Auction
from tests.algorand.test_support import AlgorandTestCase


class SearchAuctionEventsTestCase(AlgorandTestCase):
    def test_search_auction_events_by_event(self):
        logger = super().get_logger("test_search_auction_events_by_event")
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

        auction_client = seller_auction_manager_client.create_auction()

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

        # commit the auction
        start_time = datetime.now(UTC) + timedelta(days=1)
        end_time = start_time + timedelta(days=3)
        auction_client.set_bid_asset(bid_asset_id, 10_000)
        auction_client.optin_asset(gold_asset_id)
        auction_client.deposit_asset(gold_asset_id, 10_000)
        auction_client.commit(start_time, end_time)

        sleep(0.5)  # give the indexer time to index

        request = SearchAuctionEventsRequest(
            auction_app_id=auction_client.app_id,
            filter=AuctionEvent.COMMITTED,
        )
        result = search_auction_events(request)
        logger.info(result)
        self.assertEqual(AuctionEvent.COMMITTED, result.filter)
        self.assertEqual(1, len(result.txns))

        with self.subTest(
            "set the request min_round to the result max_confirmed_round"
        ):
            request = SearchAuctionEventsRequest(
                auction_app_id=auction_client.app_id,
                filter=AuctionEvent.COMMITTED,
                min_round=result.max_confirmed_round,
            )
            result = search_auction_events(request)
            logger.info(result)
            self.assertEqual(AuctionEvent.COMMITTED, result.filter)
            self.assertEqual(1, len(result.txns))

        with self.subTest(
            "set the request min_round to the result max_confirmed_round + 1"
        ):
            request = SearchAuctionEventsRequest(
                auction_app_id=auction_client.app_id,
                filter=AuctionEvent.COMMITTED,
                min_round=result.max_confirmed_round + 1,
            )
            result = search_auction_events(request)
            logger.info(result)
            self.assertEqual(AuctionEvent.COMMITTED, result.filter)
            self.assertIsNone(result.txns)

    def test_search_auction_events_by_phase(self):
        search_auction_events = SearchAuctionEvents(self.indexer)

        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()
        bidder = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        seller_auction_manager_client = creator_app_client.copy(
            sender=Address(seller.address), signer=seller.signer
        )

        auction_client = seller_auction_manager_client.create_auction()
        bidder_client = AuctionBidder(
            ApplicationClient(
                client=self.algod_client,
                app=Auction(),
                app_id=auction_client.app_id,
                signer=bidder.signer,
                sender=bidder.address,
            )
        )

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
        self._optin_asset_and_seed_balance(
            receiver=Address(bidder.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )

        # setup the auction
        auction_client.set_bid_asset(bid_asset_id, 10_000)
        auction_client.optin_asset(gold_asset_id)
        auction_client.deposit_asset(gold_asset_id, 10_000)
        # commit the auction
        start_time = auction_client.latest_timestamp()
        end_time = start_time + timedelta(days=3)
        auction_client.commit(start_time, end_time)

        bidder_client.bid(20_000)

        request = SearchAuctionEventsRequest(
            auction_app_id=auction_client.app_id,
            filter=AuctionPhase.BIDDING,
        )

        sleep(1)

        result = search_auction_events(request)
        pprint.pp(result)

        self.assertEqual(AuctionPhase.BIDDING, result.filter)
        self.assertEqual(1, len(result.txns))
        self.assertEqual(2, len(result.txns[auction_client.app_id]))

        txn_notes = [
            AppTxnNote.decode(txn.note) for txn in result.txns[auction_client.app_id]
        ]
        for note in [AuctionClient.COMMIT_NOTE, AuctionBidder.BID_NOTE]:
            self.assertIn(note, txn_notes)


if __name__ == "__main__":
    unittest.main()
