"""
Provides support to search on-chain Auction data
"""
from typing import Any

from algosdk.logic import get_application_address
from algosdk.v2client.indexer import IndexerClient

from oysterpack.algorand.client.model import AppId, Address


class AuctionIndexerClient:
    """
    Used to search on-chain Auction data
    """

    def __init__(self, indexer_client: IndexerClient, auction_manager_app_id: AppId):
        # check the app_id
        result = indexer_client.applications(application_id=auction_manager_app_id)
        print(result)

        self._indexer_client = indexer_client
        self.auction_manager_app_id = auction_manager_app_id

    @property
    def auction_manager_address(self) -> Address:
        """
        :return: AuctionManager application address
        """
        return Address(get_application_address(self.auction_manager_app_id))

    def search_auctions(
        self, limit: int = 100, next_page: str | None = None
    ) -> dict[str, Any]:
        """
        Used to search auctions
        :param limit: max number of search results to return
        :param next_page: used for pagination
        :return:
        """
        return self._indexer_client.search_applications(creator=self.auction_manager_address, limit=limit, next_page=next_page)
