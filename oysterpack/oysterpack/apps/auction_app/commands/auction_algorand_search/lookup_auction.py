"""
Command used to retrieve Auction info from Algorand
"""
from dataclasses import dataclass

from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.apps.auction_app.commands.auction_algorand_search import (
    AuctionAlgorandSearchSupport,
)
from oysterpack.apps.auction_app.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction_app.domain.auction import (
    AuctionAppId,
    Auction,
)
from oysterpack.core.command import Command


@dataclass(slots=True)
class AuctionManagerNotRegisteredError(Exception):
    """
    Raised if the Auction creator is a registered AuctionManager
    """

    auction_app_id: AppId
    auction_creator: Address


class LookupAuction(Command[AuctionAppId, Auction | None]):
    """
    Tries to look up the auction on Algorand.
    """

    def __init__(
        self,
        algod_client: AlgodClient,
        lookup_auction_manager: LookupAuctionManager,
    ):
        self._algod_client = algod_client
        self._lookup_auction_manager = lookup_auction_manager

    def __call__(self, auction_app_id: AuctionAppId) -> Auction | None:

        try:
            app_info = self._algod_client.application_info(auction_app_id)

            creator_address = app_info["params"]["creator"]
            result = self._lookup_auction_manager(creator_address)
            if result is None:
                raise AuctionManagerNotRegisteredError(
                    AppId(app_info["id"]), creator_address
                )

            (auction_manager_app_id, _address) = result

            return AuctionAlgorandSearchSupport.to_auction(
                app_info,
                self._algod_client,
                auction_manager_app_id,
            )

        except AlgodHTTPError as err:
            if err.code == 404:
                return None
            raise
