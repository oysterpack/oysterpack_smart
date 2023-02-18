"""
Provides support to search on-chain Auction data
"""
from dataclasses import dataclass
from typing import cast, Any

from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from beaker.client import ApplicationClient
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, Address, AssetHolding, AssetId
from oysterpack.apps.auction_app.client.auction_client import AuctionState
from oysterpack.apps.auction_app.contracts.auction import Auction as AuctionApp
from oysterpack.apps.auction_app.domain.auction import Auction


@dataclass
class AuctionSearchResult:
    """
    Auction search results
    """

    auctions: list[Auction]

    # the round the search was run
    round: int
    # used for paging
    next_page: str | None


class AuctionIndexerClient:
    """
    Used to search on-chain Auction data
    """

    def __init__(
        self,
        indexer_client: IndexerClient,
        algod_client: AlgodClient,
        auction_manager_app_id: AppId,
    ):
        self._indexer_client = indexer_client
        self._algod_client = algod_client
        self.auction_manager_app_id = auction_manager_app_id

    @property
    def auction_manager_address(self) -> Address:
        """
        :return: AuctionManager application address
        """
        return Address(get_application_address(self.auction_manager_app_id))

    def search_auctions(
        self,
        limit: int = 100,
        next_token: str | AppId | None = None,
    ) -> AuctionSearchResult:
        """
        Used to search auctions
        :param limit: max number of search results to return
        :param next_token: used for pagination
        :return:
        """

        result = self._indexer_client.search_applications(
            creator=self.auction_manager_address,
            limit=limit,
            next_page=str(next_token) if next_token else next_token,
        )

        current_round = result["current-round"]
        next_token = result.setdefault("next-token", None)

        def create_auction(app: dict[str, Any]) -> Auction:
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

        auctions = [create_auction(app) for app in result["applications"]]
        return AuctionSearchResult(
            round=current_round,
            next_page=cast(str | None, next_token),
            auctions=auctions,
        )
