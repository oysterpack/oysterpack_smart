"""
Command that searches Algorand for auctions to import into the database
"""
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta

from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
    AuctionSearchRequest,
)
from oysterpack.apps.auction_app.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.core.command import Command


@dataclass(slots=True)
class ImportAuctionsRequest:
    """
    ImportAuctionsRequest
    """

    auction_manager_app_id: AuctionManagerAppId

    # limits the number of auctions to fetch per Algorand search
    algorand_search_limit: int = 100


@dataclass(slots=True)
class ImportAuctionsResult:
    """
    ImportAuctionsResult
    """

    # number of new auctions that were imported into the database
    count: int

    start_time: datetime
    end_time: datetime

    error: Exception | None = None

    @property
    def import_duration(self) -> timedelta:
        return self.end_time - self.start_time


class ImportAuctions(Command[ImportAuctionsRequest, ImportAuctionsResult]):
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

    def __call__(self, request: ImportAuctionsRequest) -> ImportAuctionsResult:
        start_time = datetime.now(UTC)
        count = 0
        try:
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
                limit=request.algorand_search_limit,
                next_token=max_auction_app_id,
            )
            search_result = self._search(search_request)
            self._logger.debug(search_result)
            if len(search_result.auctions) == 0:
                return ImportAuctionsResult(
                    count=count,
                    start_time=start_time,
                    end_time=datetime.now(UTC),
                )

            store_result = self._store(search_result.auctions)
            self._logger.info(store_result)
            count += store_result.inserts

            while search_result.next_token is not None:
                search_request.next_token = search_result.next_token
                search_result = self._search(search_request)
                self._logger.debug(search_result)

                store_result = self._store(search_result.auctions)
                self._logger.info(store_result)
                count += store_result.inserts

            return ImportAuctionsResult(
                count=count,
                start_time=start_time,
                end_time=datetime.now(UTC),
            )
        except Exception as err:
            return ImportAuctionsResult(
                count=count,
                start_time=start_time,
                end_time=datetime.now(UTC),
                error=err,
            )
