"""
Provides command support for searching Auctions
"""
from dataclasses import dataclass
from typing import Any, cast

from algosdk.logic import get_application_address
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, AssetId, AssetHolding, Address
from oysterpack.apps.auction_app.client.auction_client import (
    to_auction_state,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_support import (
    AuctionAlgorandSearchSupport,
)
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.core.command import Command


@dataclass(slots=True)
class AuctionSearchRequest:
    """
    Auction search args
    """

    # auction creator
    auction_manager_app_id: AppId

    # max number of search results to return
    limit: int = 100

    # used for paging
    # search results are sorted by AppId, i.e., search will return auctions where app ID is > `next_token`
    next_token: str | AppId | None = None

    def __post_init__(self):
        if isinstance(self.next_token, AppId):
            self.next_token = str(self.next_token)

    @property
    def auction_manager_address(self) -> Address:
        """
        :return: AuctionManager application address
        """
        return Address(get_application_address(self.auction_manager_app_id))


@dataclass(slots=True)
class AuctionSearchResult:
    """
    Auction search results
    """

    auctions: list[Auction]

    # used for paging
    next_token: str | None


class SearchAuctions(
    Command[AuctionSearchRequest, AuctionSearchResult],
    AuctionAlgorandSearchSupport,
):
    """
    Used to search for Auction apps on Algorand.
    """

    def __call__(self, args: AuctionSearchRequest) -> AuctionSearchResult:
        result = self._indexer_client.search_applications(
            creator=args.auction_manager_address,
            limit=args.limit,
            next_page=args.next_token,
        )

        current_round = result["current-round"]
        next_token = result.setdefault("next-token", None)

        def to_auction(app: dict[str, Any]) -> Auction:
            def get_auction_assets(
                app_id: AppId,
                bid_asset_id: AssetId | None,
            ) -> dict[AssetId, int]:
                app_address = get_application_address(app_id)
                auction_assets = [
                    AssetHolding.from_data(asset)
                    for asset in self._algod_client.account_info(app_address)["assets"]
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
                auction_manager_app_id=args.auction_manager_app_id,
                created_at_round=app["created-at-round"],
                state=state,
                assets=get_auction_assets(AppId(app["id"]), state.bid_asset_id),
                round=current_round,
            )

        auctions = [to_auction(app) for app in result["applications"]]
        return AuctionSearchResult(
            auctions=auctions,
            next_token=cast(str | None, next_token),
        )
