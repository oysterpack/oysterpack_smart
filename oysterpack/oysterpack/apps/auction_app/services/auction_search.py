"""
Provides auction search capabilities
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from oysterpack.algorand.client.model import Address, AssetId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.domain.auction import Auction


@dataclass(slots=True)
class SearchResults:
    """
    Search results
    """

    auction: list[Auction]

    total_hits: int
    # used for paging results
    # if not None, then it can be used to retrieve the next
    bookmark: str | None


class AuctionSearch(ABC):
    @abstractmethod
    def total_counts_by_status(
        self, seller_address: Address | None
    ) -> dict[AuctionStatus, int]:
        """
        :param seller_address: if not None, then auction counts will be returned  for the specified seller
        :return: total number of Auction contracts for each status
        """

    @abstractmethod
    def search(
        self,
        seller_address: Address | None = None,
        status: AuctionStatus | None = None,
        bid_asset_id: AssetId | None = None,
        min_bid: int | None = None,
    ) -> SearchResults:
        ...
