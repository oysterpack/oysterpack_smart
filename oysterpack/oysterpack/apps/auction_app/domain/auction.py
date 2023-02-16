"""
Auction domain model
"""

from dataclasses import dataclass
from datetime import datetime

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus


@dataclass(slots=True)
class Auction:
    """
    Auction
    """

    # pylint: disable=too-many-instance-attributes

    app_id: AppId
    created_on: datetime

    seller_address: Address
    status: AuctionStatus

    bid_asset_id: AssetId | None
    min_bid: int | None

    auction_assets: dict[AssetId, int]

    highest_bidder_address: Address | None
    highest_bid: int | None

    start_time: datetime | None
    end_time: datetime | None
