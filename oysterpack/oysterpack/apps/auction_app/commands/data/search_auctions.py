from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from enum import auto

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus


@dataclass(slots=True)
class AuctionSortField(IntEnum):
    Status = auto()
    Seller = auto()
    MinBid = auto()
    HighestBid = auto()
    StartTime = auto()
    EndTime = auto()
    AssetAmount = auto()


@dataclass(slots=True)
class AuctionSort:
    """
    Auction.app_id is always append to the sort field.
    """

    field: AuctionSortField
    asc: bool = True  # sort order, i.e., ascending or descending


@dataclass(slots=True)
class AuctionSearchFilters:
    app_id: set[AppId] = field(default_factory=set)

    status: set[AuctionStatus] = field(default_factory=set)
    seller: set[Address] = field(default_factory=set)

    bid_asset_id: set[AssetId] = field(default_factory=set)
    min_bid: int | None = None  # min_bid >= Auction.min_bid

    highest_bidder: set[Address] = field(default_factory=set)
    highest_bid: int | None = None  # highest_bid >= Auction.highest_bid

    start_time: datetime | None = None  # start_time >= Auction.start_time
    end_time: datetime | None = None  # end_time >= Auction.end_time

    assets: set[AssetId] = field(default_factory=set)
    asset_amounts: dict[AssetId, int] = field(default_factory=dict)

    sort: AuctionSort | None = None
    limit: int = 100
    offset: int = 0
