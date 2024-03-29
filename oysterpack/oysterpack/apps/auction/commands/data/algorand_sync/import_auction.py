"""
Provides a command that imports an Auction from Algorand into the database.
"""

from oysterpack.apps.auction.commands.auction_algorand_search.lookup_auction import (
    LookupAuction,
)
from oysterpack.apps.auction.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.domain.auction import (
    AuctionAppId,
    Auction,
)
from oysterpack.core.logging import get_logger


class ImportAuction:
    """
    Imports the Auction from Algorand into the database.

    Notes
    -----
    - If the auction does not exist on Algorand, but exists in the database, then it will be deleted from the database.
    - If the auction exists in Algorand, then it will be inserted or updated in the database.
    """

    def __init__(
        self,
        lookup: LookupAuction,
        store: StoreAuctions,
        delete: DeleteAuctions,
    ):
        self._lookup_auction = lookup
        self._store = store
        self._delete = delete

        self._logger = get_logger(self)

    def __call__(self, auction_app_id: AuctionAppId) -> Auction | None:
        auction = self._lookup_auction(auction_app_id)
        if auction is None:
            self._delete([auction_app_id])
        else:
            self._store([auction])

        return auction
