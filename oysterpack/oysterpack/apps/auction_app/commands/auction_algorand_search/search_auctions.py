"""
Provides command support for searching Auctions
"""
from dataclasses import dataclass
from typing import cast

from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.apps.auction_app.commands.auction_algorand_search import to_auction
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


class SearchAuctions(Command[AuctionSearchRequest, AuctionSearchResult]):
    """
    Used to search for Auction apps on Algorand.
    """

    def __init__(
        self,
        indexer_client: IndexerClient,
        algod_client: AlgodClient,
    ):
        self._indexer_client = indexer_client
        self._algod_client = algod_client

    def __call__(self, args: AuctionSearchRequest) -> AuctionSearchResult:
        result = self._indexer_client.search_applications(
            creator=args.auction_manager_address,
            limit=args.limit,
            next_page=args.next_token,
        )

        next_token = result.setdefault("next-token", None)

        auctions = [
            to_auction(
                app,
                self._algod_client,
                args.auction_manager_app_id,
            )
            for app in result["applications"]
        ]
        return AuctionSearchResult(
            auctions=auctions,
            next_token=cast(str | None, next_token),
        )
