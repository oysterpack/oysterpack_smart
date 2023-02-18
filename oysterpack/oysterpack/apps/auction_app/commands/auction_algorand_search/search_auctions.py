"""
Provides command support for searching Auctions
"""
from dataclasses import dataclass
from typing import Any, cast

from beaker.client import ApplicationClient
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, AssetId, AssetHolding
from oysterpack.apps.auction_app.client.auction_client import AuctionState
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_support import (
    AuctionAlgorandSearchSupport,
)
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.core.command import Command
from oysterpack.apps.auction_app.contracts.auction import Auction as AuctionApp


@dataclass
class AuctionSearchArgs:
    """
    Auction search args
    """

    # max number of search results to return
    limit: int = 100

    # used for paging
    # search results are sorted by AppId
    next_token: str | AppId | None = None

    def __post_init__(self):
        if isinstance(self.next_token, AppId):
            self.next_token = str(self.next_token)


@dataclass
class AuctionSearchResult:
    """
    Auction search results
    """

    auctions: list[Auction]

    # the round the search was run
    round: int
    # used for paging
    next_token: str | None


class SearchAuctions(
    Command[AuctionSearchArgs, AuctionSearchResult], AuctionAlgorandSearchSupport
):
    def __call__(self, args: AuctionSearchArgs) -> AuctionSearchResult:
        result = self._indexer_client.search_applications(
            creator=self.auction_manager_address,
            limit=args.limit,
            next_page=args.next_token,
        )

        current_round = result["current-round"]
        next_token = result.setdefault("next-token", None)

        def to_auction(app: dict[str, Any]) -> Auction:
            def get_auction_assets(
                app_id: AppId, bid_asset_id: AssetId | None
            ) -> list[AssetHolding]:
                app_client = ApplicationClient(
                    self._algod_client, AuctionApp(), app_id=app_id
                )
                auction_assets = [
                    AssetHolding.from_data(asset)
                    for asset in app_client.get_application_account_info()["assets"]
                ]

                # filter out the bid asset
                if bid_asset_id:
                    return [
                        asset
                        for asset in auction_assets
                        if asset.asset_id != bid_asset_id
                    ]
                return auction_assets

            state = AuctionState(
                cast(
                    dict[bytes | str, bytes | str | int],
                    decode_state(app["params"]["global-state"]),
                )
            )

            return Auction(
                app_id=AppId(app["id"]),
                creator=app["params"]["creator"],
                created_at_round=app["created-at-round"],
                state=state,
                auction_assets=get_auction_assets(AppId(app["id"]), state.bid_asset_id),
            )

        auctions = [to_auction(app) for app in result["applications"]]
        return AuctionSearchResult(
            round=current_round,
            next_token=cast(str | None, next_token),
            auctions=auctions,
        )
