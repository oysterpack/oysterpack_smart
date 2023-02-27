"""
Command that searches Algorand for auctions to import into the database
"""
from builtins import NotImplementedError
from dataclasses import dataclass

from oysterpack.apps.auction_app.commands.auction_algorand_search.lookup_auction import (
    LookupAuction,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.domain.auction import (
    AuctionAppId,
    AuctionManagerAppId,
    Auction,
)
from oysterpack.core.command import Command


@dataclass(slots=True)
class ImportAuctionRequest:
    """
    ImportAuctionRequest
    """

    auction_manager_app_id: AuctionManagerAppId
    auction_app_id: AuctionAppId


class ImportAuction(Command[ImportAuctionRequest, Auction | None]):
    """
    Lookup the auction on Algorand and imports it into the database.

    Notes
    -----
    - If the auction does not exist on Algorand, but exists in the database, then it will be deleted from the database.
    - If the auction exists in Algorand, then it will be either inserted or updated in the database.


    """

    def __init__(
        self,
        lookup_auction: LookupAuction,
        store: StoreAuctions,
    ):
        self._lookup_auction = lookup_auction
        self._store = store
        self._logger = super().get_logger()

    def __call__(self, request: ImportAuctionRequest) -> Auction | None:
        raise NotImplementedError
