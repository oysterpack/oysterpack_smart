import unittest
from time import sleep

from oysterpack.algorand.client.model import Address, AppId
from oysterpack.apps.auction.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction.commands.auction_algorand_search.search_auction_manager_events import (
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
            event: AuctionManagerEvent,
            expected_auction_app_ids: list[AppId] | None,
        ):
            """
            :param event: event to search for
            :param expected_auction_app_ids: the expected auction app IDs that should match auction app IDs in
                                             the search result
            """
            request = SearchAuctionManagerEventsRequest(
                auction_manager_app_id=creator_app_client.app_id,
                event=event,
            )
            result = search_auction_events(request)
            logger.info(result)
            self.assertEqual(event, result.event)
            if expected_auction_app_ids is None:
                self.assertIsNone(result.auction_txns)
            else:
                self.assertEqual(
                    len(expected_auction_app_ids), len(result.auction_txns)
                )
                for app_id in expected_auction_app_ids:
                    self.assertIn(app_id, result.auction_txns)

                # check the confirmed round
                for txn in result.auction_txns.values():
                    txn_info = self.indexer.transaction(txn.id)
                    self.assertEqual(
                        txn.confirmed_round, txn_info["transaction"]["confirmed-round"]
                    )

                    # test min_round filter
                    confirmed_round = txn.confirmed_round
                    request = SearchAuctionManagerEventsRequest(
                        auction_manager_app_id=creator_app_client.app_id,
                        event=event,
                        min_round=confirmed_round,
                    )
                    result = search_auction_events(request)
                    self.assertIsNotNone(result.auction_txns)
                    for txn in result.auction_txns.values():
                        self.assertGreaterEqual(txn.confirmed_round, confirmed_round)

                    # when min_round is greater than latest confirmed round
                    request = SearchAuctionManagerEventsRequest(
                        auction_manager_app_id=creator_app_client.app_id,
                        event=event,
                        min_round=confirmed_round + 10,
                    )
                    result = search_auction_events(request)
                    # then we expect no txn events
                    self.assertIsNone(result.auction_txns)

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

        with self.subTest("when no auctions have yet been created"):
            search_events(AuctionManagerEvent.AUCTION_CREATED, None)
            search_events(AuctionManagerEvent.AUCTION_DELETED, None)

        with self.subTest("when auctions have been created"):
            # create auctions
            auction_clients = []
            for _ in range(2):
                auction_client = seller_auction_manager_client.create_auction()
                auction_client.cancel()
                auction_client.finalize()
                auction_clients.append(auction_client)
            sleep(0.5)
            auction_client_app_ids = [
                auction_client.app_id for auction_client in auction_clients
            ]

            search_events(AuctionManagerEvent.AUCTION_CREATED, auction_client_app_ids)
            search_events(AuctionManagerEvent.AUCTION_DELETED, None)

        with self.subTest("when auctions have been deleted"):
            for auction_client in auction_clients:
                creator_app_client.delete_finalized_auction(auction_client.app_id)
            sleep(0.5)

            search_events(AuctionManagerEvent.AUCTION_CREATED, auction_client_app_ids)
            search_events(AuctionManagerEvent.AUCTION_DELETED, auction_client_app_ids)


if __name__ == "__main__":
    unittest.main()
