"""
Command used to retrieve Auction info from Algorand
"""
from dataclasses import dataclass
from typing import Any, cast

from algosdk.error import IndexerHTTPError
from algosdk.logic import get_application_address
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, AssetId, AssetHolding
from oysterpack.apps.auction_app.client.auction_client import to_auction_state
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_support import (
    AuctionAlgorandSearchSupport,
)
from oysterpack.apps.auction_app.domain.auction import (
    AuctionAppId,
    Auction,
    AuctionManagerAppId,
)
from oysterpack.core.command import Command


@dataclass(slots=True)
class LookupAuctionRequest:
    auction_app_id: AuctionAppId
    auction_manager_app_id: AuctionManagerAppId


@dataclass(slots=True)
class LookupAuctionResult:
    auction: Auction | None
    deleted: bool


class LookupAuction(
    Command[LookupAuctionRequest, LookupAuctionResult],
    AuctionAlgorandSearchSupport,
):
    """
    Runs an Algorand indexer search to lookup up the auction.
    Deletes are detected.

    Asserts
    -------
    1. auction creator address matches the expected auction manager
    """

    def __call__(self, request: LookupAuctionRequest) -> LookupAuctionResult:
        try:
            result = self._indexer_client.applications(
                request.auction_app_id,
                include_all=True,  # include all to detect deletes
            )

            if result["application"]["deleted"]:
                return LookupAuctionResult(auction=None, deleted=True)

            auction_manager_address = get_application_address(
                request.auction_manager_app_id
            )
            if auction_manager_address != result["application"]["params"]["creator"]:
                raise ValueError(
                    "invalid `auction_manager_app_id` - does not match auction creator"
                )

            current_round = result["current-round"]

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
                    created_at_round=app["created-at-round"],
                    state=state,
                    assets=get_auction_assets(AppId(app["id"]), state.bid_asset_id),
                    round=current_round,
                )

            return LookupAuctionResult(
                auction=to_auction(result["application"]), deleted=False
            )
        except IndexerHTTPError as err:
            if "no application found" in str(err):
                return LookupAuctionResult(auction=None, deleted=False)
            raise
