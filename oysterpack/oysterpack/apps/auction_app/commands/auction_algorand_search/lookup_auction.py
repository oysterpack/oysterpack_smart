"""
Command used to retrieve Auction info from Algorand
"""
from typing import Any, cast

from algosdk.error import AlgodHTTPError
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, AssetId, AssetHolding
from oysterpack.apps.auction_app.client.auction_client import to_auction_state
from oysterpack.apps.auction_app.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction_app.domain.auction import (
    AuctionAppId,
    Auction,
)
from oysterpack.core.command import Command


class LookupAuction(Command[AuctionAppId, Auction | None]):
    """
    Tries to look up the auction on Algorand.

    Asserts
    -------
    1. auction creator address matches the expected auction manager
    """

    def __init__(
        self,
        algod_client: AlgodClient,
        lookup_auction_manager: LookupAuctionManager,
    ):
        self._algod_client = algod_client
        self._lookup_auction_manager = lookup_auction_manager

    def __call__(self, auction_app_id: AuctionAppId) -> Auction | None:
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

            creator_address = app_info["params"]["creator"]
            result = self._lookup_auction_manager(creator_address)
            if result is None:
                raise AssertionError(
                    f"auction manager is not registered in the database: {creator_address}"
                )

            (auction_manager_app_id, _address) = result

            return Auction(
                app_id=AppId(app["id"]),
                auction_manager_app_id=auction_manager_app_id,
                state=state,
                assets=get_auction_assets(AppId(app["id"]), state.bid_asset_id),
            )

        try:
            app_info = self._algod_client.application_info(auction_app_id)
            return to_auction(app_info)

        except AlgodHTTPError as err:
            if err.code == 404:
                return None
            raise
