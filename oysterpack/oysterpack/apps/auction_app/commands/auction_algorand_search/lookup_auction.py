"""
Command used to retrieve Auction info from Algorand
"""
import pprint
from dataclasses import dataclass
from typing import Any, cast

from algosdk.error import AlgodHTTPError
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, AssetId, AssetHolding
from oysterpack.apps.auction_app.client.auction_client import to_auction_state
from oysterpack.apps.auction_app.domain.auction import (
    AuctionAppId,
    Auction,
    AuctionManagerAppId,
)
from oysterpack.core.command import Command


@dataclass(slots=True)
class LookupAuctionRequest:
    """
    LookupAuctionRequest
    """

    auction_app_id: AuctionAppId

    # used to verify the auction creator, i.e.,
    # the auction creator address must match the auction manager contract address
    auction_manager_app_id: AuctionManagerAppId


class LookupAuction(Command[LookupAuctionRequest, Auction | None]):
    """
    Tries to look up the auction on Algorand.

    Asserts
    -------
    1. auction creator address matches the expected auction manager
    """

    def __init__(self, algod_client: AlgodClient):
        self._algod_client = algod_client

    def __call__(self, request: LookupAuctionRequest) -> Auction | None:
        def to_auction(app: dict[str, Any]) -> Auction:
            def get_auction_assets(
                app_id: AppId,
                bid_asset_id: AssetId | None,
            ) -> dict[AssetId, int]:
                app_address = get_application_address(app_id)
                account_info = self._algod_client.account_info(app_address)
                auction_assets = [
                    AssetHolding.from_data(asset)
                    for asset in account_info["assets"]
                    if asset["asset-id"] != bid_asset_id
                ]

                return {
                    asset_holding.asset_id: asset_holding.amount
                    for asset_holding in auction_assets
                }

            state = to_auction_state(
                cast(
                    dict[bytes | str, bytes | str | int],
                    decode_state(app["params"]["global-state"]),
                )
            )

            return Auction(
                app_id=AppId(app["id"]),
                auction_manager_app_id=request.auction_manager_app_id,
                state=state,
                assets=get_auction_assets(AppId(app["id"]), state.bid_asset_id),
            )

        try:
            app_info = self._algod_client.application_info(request.auction_app_id)
            pprint.pp(app_info)

            auction_manager_address = get_application_address(
                request.auction_manager_app_id
            )
            if auction_manager_address != app_info["params"]["creator"]:
                raise ValueError(
                    "invalid `auction_manager_app_id` - does not match auction creator"
                )

            return to_auction(app_info)

        except AlgodHTTPError as err:
            if err.code == 404:
                return None
            raise
