"""
Provides Command that searches Algorand for auctions to import into the database
"""
from dataclasses import dataclass

from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
    AuctionSearchResult,
)
from oysterpack.apps.auction_app.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.domain.auction import (
    AuctionManagerAppId,
    Auction,
    AuctionAppId,
)
from oysterpack.core.logging import get_logger


@dataclass(slots=True)
class ImportAuctionsRequest:
    """
    ImportAuctionsRequest
    """

    auction_manager_app_id: AuctionManagerAppId

    # max number of auctions to import in this batch
    batch_size: int = 100


class ImportAuctions:
    """
    Searches Algorand for Auctions to import into the database.
    """

    def __init__(
        self,
        search: SearchAuctions,
        store: StoreAuctions,
        get_max_auction_app_id: GetMaxAuctionAppId,
    ):
        self._search = search
        self._store = store
        self._get_max_auction_app_id = get_max_auction_app_id
        self._logger = get_logger(self)

    def __call__(self, request: ImportAuctionsRequest) -> list[Auction]:
        # app ID is used as the next token
        # query the database to get the max auction app ID to pick up where we left off
        max_auction_app_id = self.__get_max_auction_app_id(
            request.auction_manager_app_id
        )
        search_result = self.__search(request, max_auction_app_id)
        if len(search_result.auctions) == 0:
            return []
        self.__store(search_result.auctions)
        return search_result.auctions

    def __get_max_auction_app_id(
        self, auction_manager_app_id: AuctionManagerAppId
    ) -> AuctionAppId | None:
        max_auction_app_id = self._get_max_auction_app_id(auction_manager_app_id)
        self._logger.info(
            "auction_manager_app_id = %s, max_auction_app_id = %s",
            auction_manager_app_id,
            max_auction_app_id,
        )
        return max_auction_app_id

    def __search(
        self, request: ImportAuctionsRequest, max_auction_app_id: AuctionAppId | None
    ) -> AuctionSearchResult:
        search_request = AuctionSearchRequest(
            auction_manager_app_id=request.auction_manager_app_id,
            limit=request.batch_size,
            next_token=max_auction_app_id,
        )
        search_result = self._search(search_request)
        self._logger.debug(search_result)
        return search_result

    def __store(self, auctions: list[Auction]):
        store_result = self._store(auctions)
        self._logger.info(store_result)
