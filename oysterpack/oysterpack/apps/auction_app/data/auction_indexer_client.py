"""
Provides support to search on-chain Auction data
"""
from typing import Any

from algosdk.logic import get_application_address
from algosdk.v2client.indexer import IndexerClient

from oysterpack.algorand.client.model import AppId


class AuctionIndexerClient:
    def __init__(self, indexer_client: IndexerClient, auction_manager_app_id: AppId):
        # check the app_id
        result = indexer_client.applications(application_id=auction_manager_app_id)
        print(result)

        self._indexer_client = indexer_client
        self.auction_manager_app_id = auction_manager_app_id
        self.auction_manager_address = get_application_address(auction_manager_app_id)

    def list_auctions(
        self, limit: int = 100, next_page: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError
