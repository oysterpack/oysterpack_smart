"""
Provides Algorand search support
"""
from typing import Any, cast

from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, AssetId, AssetHolding
from oysterpack.apps.auction_app.client.auction_client import to_auction_state
from oysterpack.apps.auction_app.domain.auction import Auction


class AuctionAlgorandSearchSupport:
    """
    Provides support for searching Algorand on-chain data for Auction apps
    """

    # pylint: disable=too-few-public-methods

    def __init__(
        self,
        indexer_client: IndexerClient,
        algod_client: AlgodClient,
    ):
        self._indexer_client = indexer_client
        self._algod_client = algod_client

    @staticmethod
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
            account_info = algod_client.account_info(app_address)
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
            auction_manager_app_id=auction_manager_app_id,
            state=state,
            assets=get_auction_assets(AppId(app["id"]), state.bid_asset_id),
        )
