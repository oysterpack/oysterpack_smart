"""
Provides Algorand search support
"""
from typing import Any, cast

from algokit_utils.application_client import _decode_state
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.model import AppId, AssetId, AssetHolding
from oysterpack.apps.auction.client.auction_client import to_auction_state
from oysterpack.apps.auction.domain.auction import Auction


def to_auction(
    app: dict[str, Any],
    algod_client: AlgodClient,
    auction_manager_app_id: AppId,
) -> Auction:
    """
    Converts application info retrieved from Algorand into an Auction.
    """

    def get_auction_assets(
        app_id: AppId,
        bid_asset_id: AssetId | None,
    ) -> dict[AssetId, int]:
        app_address = get_application_address(app_id)
        account_info = cast(dict[str, Any], algod_client.account_info(app_address))
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
            _decode_state(app["params"]["global-state"]),
        )
    )

    return Auction(
        app_id=AppId(app["id"]),
        auction_manager_app_id=auction_manager_app_id,
        state=state,
        assets=get_auction_assets(AppId(app["id"]), state.bid_asset_id),
    )
