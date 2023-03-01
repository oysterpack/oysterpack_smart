"""
Refresh auctions that are stored in the database with Algorand
"""
from oysterpack.apps.auction_app.commands.data.algorand_sync.import_auction import (
    ImportAuction,
)
from oysterpack.apps.auction_app.commands.data.errors import (
    AuctionManagerNotRegisteredError,
)
from oysterpack.apps.auction_app.domain.auction import AuctionAppId, Auction
from oysterpack.core.command import Command

RefreshAuctionsResult = dict[
    AuctionAppId, Auction | None | AuctionManagerNotRegisteredError
]


class RefreshAuctions(Command[list[AuctionAppId], RefreshAuctionsResult]):
    """
    If the Auction exists on Algorand, then its state will be imported into the database.
    Otherwise, the Auction will be deleted from the database.

    Notes
    -----
    - The auction will fail to import if its creator is not a registered AuctionManager in the database.
    """

    def __init__(self, import_auction: ImportAuction):
        self._import = import_auction

    def __call__(self, auction_app_ids: list[AuctionAppId]) -> RefreshAuctionsResult:
        result: RefreshAuctionsResult = {}
        for app_id in auction_app_ids:
            try:
                result[app_id] = self._import(app_id)
            except AuctionManagerNotRegisteredError as err:
                result[app_id] = err

        return result
