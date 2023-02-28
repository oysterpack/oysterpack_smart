"""
Provides command to delete finalized auctions
"""
from dataclasses import dataclass

from oysterpack.apps.auction_app.client.auction_manager_client import (
    AuctionManagerClient,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.app_exists import (
    AppExists,
)
from oysterpack.apps.auction_app.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction_app.commands.data.errors import (
    AuctionManagerNotRegisteredError,
)
from oysterpack.apps.auction_app.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction_app.commands.data.queries.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
    AuctionSearchFilters,
    AuctionSearchResult,
)
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.core.command import Command


@dataclass(slots=True)
class DeleteFinalizedAuctionsRequest:
    """
    DeleteFinalizedAuctionsRequest
    """

    auction_manager_app_id: AuctionManagerAppId

    batch_size: int = 100


class DeleteFinalizedAuctions(Command[DeleteFinalizedAuctionsRequest, int]):
    """
    Deletes finalized auctions on ALgorand and from the database.
    """

    def __init__(
        self,
        search_auctions: SearchAuctions,
        delete_auctions: DeleteAuctions,
        app_exists: AppExists,
        lookup_auction_manager: LookupAuctionManager,
        auction_manager_client: AuctionManagerClient,
    ):
        self._search = search_auctions
        self._delete = delete_auctions
        self._app_exists_on_algorand = app_exists
        self._lookup_auction_manager = lookup_auction_manager
        self._auction_manager_client = auction_manager_client
        self._logger = super().get_logger()

    def __call__(self, request: DeleteFinalizedAuctionsRequest) -> int:
        self._validate_request(request)
        self._logger.info(request)

        search_request = AuctionSearchRequest(
            filters=AuctionSearchFilters(
                auction_manager_app_id={request.auction_manager_app_id},
                status={AuctionStatus.FINALIZED},
            ),
            limit=request.batch_size,
        )
        search_results = self._search(search_request)
        self._logger.info(
            "finalized auction total count = %s", search_results.total_count
        )
        if len(search_results.auctions) == 0:
            return 0

        delete_count = self._delete_auctions(search_results)
        self._logger.info("PROCESSING: delete count = %s", delete_count)

        while search_request.next_page(search_results):
            search_results = self._search(search_request)
            if len(search_results.auctions) == 0:
                return delete_count

            delete_count += self._delete_auctions(search_results)
            self._logger.info("PROCESSING: delete count = %s", delete_count)

        self._logger.info("DONE: delete count = %s", delete_count)
        return delete_count

    def _validate_request(self, request: DeleteFinalizedAuctionsRequest):
        if request.batch_size <= 0:
            raise AssertionError("`batch_size` must be greater than zero")

        if self._lookup_auction_manager(request.auction_manager_app_id) is None:
            raise AuctionManagerNotRegisteredError

    def _delete_auctions(self, search_results: AuctionSearchResult) -> int:
        for auction in search_results.auctions:
            if self._app_exists_on_algorand(auction.app_id):
                self._auction_manager_client.delete_finalized_auction(auction.app_id)

        self._delete([auction.app_id for auction in search_results.auctions])
        return len(search_results.auctions)
