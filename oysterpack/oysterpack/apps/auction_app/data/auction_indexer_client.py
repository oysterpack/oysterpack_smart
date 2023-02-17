"""
Provides support to search on-chain Auction data
"""
from dataclasses import dataclass
from typing import cast

from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from beaker.client.state_decode import decode_state

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.apps.auction_app.client.auction_client import AuctionState
from oysterpack.apps.auction_app.domain.auction import Auction


@dataclass
class AuctionSearchResult:
    auctions: list[Auction]
    round: int
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
        next_page: str | None = None,
    ) -> AuctionSearchResult:
        """
        Used to search auctions
        :param limit: max number of search results to return
        :param next_page: used for pagination
        :return:
        """
        result = self._indexer_client.search_applications(
            creator=self.auction_manager_address,
            limit=limit,
            next_page=next_page,
        )

        current_round = result["current-round"]
        next_page = result.setdefault("next-token", None)

        auctions = [
            Auction(
                app_id=AppId(app["id"]),
                creator=app["params"]["creator"],
                created_at_round=app["created-at-round"],
                state=AuctionState(
                    cast(
                        dict[bytes | str, bytes | str | int],
                        decode_state(app["params"]["global-state"]),
                    )
                ),
            )
            for app in result["applications"]
        ]
        return AuctionSearchResult(
            round=current_round, next_page=next_page, auctions=auctions
        )
