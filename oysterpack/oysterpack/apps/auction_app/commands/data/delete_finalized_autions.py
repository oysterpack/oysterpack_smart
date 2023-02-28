"""
Provides command to delete finalized auctions
"""
from oysterpack.apps.auction_app.client.auction_manager_client import (
    AuctionManagerClient,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.app_exists import (
    AppExists,
)
from oysterpack.apps.auction_app.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction_app.commands.data.queries.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
    AuctionSearchFilters,
)
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.core.command import Command


class DeleteFinalizedAuctions(Command[AuctionManagerAppId, int]):
    """
    Deletes finalized auctions on ALgorand and from the database.
    """

    def __init__(
        self,
        search_auctions: SearchAuctions,
        delete_auctions: DeleteAuctions,
        app_exists: AppExists,
        auction_manager_client: AuctionManagerClient,
    ):
        self._search = search_auctions
        self._delete = delete_auctions
        self._app_exists_on_algorand = app_exists
        self._auction_manager_client = auction_manager_client

    def __call__(self, auction_manager_app_id: AuctionManagerAppId) -> int:
        search_request = AuctionSearchRequest(
            filters=AuctionSearchFilters(
                auction_manager_app_id={auction_manager_app_id},
                status={AuctionStatus.FINALIZED},
            )
        )
        search_results = self._search(search_request)
        if len(search_results.auctions) == 0:
            return 0

        delete_count = 0

        for auction in search_results.auctions:
            if self._app_exists_on_algorand(auction.app_id):
                self._auction_manager_client.delete_finalized_auction(auction.app_id)

        self._delete([auction.app_id for auction in search_results.auctions])
        delete_count += len(search_results.auctions)

        while search_request.next_page(search_results):
            search_results = self._search(search_request)
            if len(search_results.auctions) == 0:
                return delete_count

            for auction in search_results.auctions:
                if self._app_exists_on_algorand(auction.app_id):
                    self._auction_manager_client.delete_finalized_auction(
                        auction.app_id
                    )

            self._delete([auction.app_id for auction in search_results.auctions])
            delete_count += len(search_results.auctions)

        return delete_count
