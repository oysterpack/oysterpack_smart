"""
Command that searches Algorand for auctions to import into the database
"""
from dataclasses import dataclass
from datetime import datetime

from oysterpack.algorand.client.model import AppId
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
)
from oysterpack.apps.auction_app.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.core.command import Command


@dataclass
class ImportAuctionsRequest:
    auction_manager_app_id: AppId

    # if not specified, then the max auction app ID will be looked up from the database
    starting_from_auction_app_id: AppId | None


@dataclass
class ImportAuctionsResult:
    count: int

    start_time: datetime
    end_time: datetime

    error: Exception | None = None


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

    def __call__(self, request: ImportAuctionsRequest) -> ImportAuctionsResult:
        raise NotImplementedError
