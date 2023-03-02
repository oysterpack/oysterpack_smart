"""
Provides Command that searches Algorand for auctions to import into the database
"""
from dataclasses import dataclass

from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
)
from oysterpack.apps.auction_app.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId, Auction
from oysterpack.core.command import Command


@dataclass(slots=True)
class ImportAuctionsRequest:
    """
    ImportAuctionsRequest
    """

    auction_manager_app_id: AuctionManagerAppId

    # max number of auctions to import in this batch
    batch_size: int = 100


class ImportAuctions(Command[ImportAuctionsRequest, list[Auction]]):
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
        self._logger = super().get_logger()

    def __call__(self, request: ImportAuctionsRequest) -> list[Auction]:
        max_auction_app_id = self._get_max_auction_app_id(
            request.auction_manager_app_id
        )
        self._logger.info(
            "auction_manager_app_id = %s, max_auction_app_id = %s",
            request.auction_manager_app_id,
            max_auction_app_id,
        )

        search_request = AuctionSearchRequest(
            auction_manager_app_id=request.auction_manager_app_id,
            limit=request.batch_size,
            next_token=max_auction_app_id,
        )
        search_result = self._search(search_request)
        self._logger.debug(search_result)
        if len(search_result.auctions) == 0:
            return []

        store_result = self._store(search_result.auctions)
        self._logger.info(store_result)
        return search_result.auctions
