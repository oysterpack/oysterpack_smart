"""
Command that searches Algorand for auctions to import into the database
"""
from builtins import NotImplementedError
from dataclasses import dataclass
from datetime import datetime, timedelta

from oysterpack.apps.auction_app.commands.auction_algorand_search.lookup_auction import LookupAuction
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.domain.auction import AuctionAppId, AuctionManagerAppId
from oysterpack.core.command import Command


@dataclass(slots=True)
class ImportAuctionRequest:
    auction_app_id: AuctionAppId
    auction_manager_app_id: AuctionManagerAppId

@dataclass(slots=True)
class ImportAuctionResult:
    """
    ImportAuctionResult
    """

    insert_count: int
    update_count: int

    start_time: datetime
    end_time: datetime

    error: Exception | None = None

    @property
    def import_duration(self) -> timedelta:
        return self.end_time - self.start_time


class ImportAuction(Command[ImportAuctionRequest, ImportAuctionResult]):
    """
    Lookup the auction on Algorand and imports it into the database.
    Deletes are handled as well, i.e., if the auction was deleted on Algorand, then it will be deleted from
    the database.
    """

    def __init__(
        self,
        lookup_auction: LookupAuction,
        store: StoreAuctions,
    ):
        self._lookup_auction = lookup_auction
        self._store = store
        self._logger = super().get_logger()

    def __call__(self, request: ImportAuctionRequest) -> ImportAuctionResult:
        # start_time = datetime.now(UTC)
        # insert_count = 0
        # update_count = 0

        raise NotImplementedError
