"""
Auction application state
"""

from dataclasses import dataclass
from datetime import datetime, UTC

from oysterpack.algorand.client.model import Address, AssetId
from oysterpack.apps.auction.contracts.auction_status import AuctionStatus


@dataclass(slots=True)
class AuctionState:
    """
    Auction application contract state
    """

    # pylint: disable=too-many-instance-attributes

    status: AuctionStatus
    seller: Address

    bid_asset_id: AssetId | None = None
    min_bid: int | None = None

    highest_bidder: Address | None = None
    highest_bid: int = 0

    start_time: datetime | None = None
    end_time: datetime | None = None

    def __post_init__(self):
        # timestamps are specified in EPOCH time
        # only second precision is needed - thus remove the sub-second precision
        if self.start_time:
            self.start_time = datetime.fromtimestamp(
                int(self.start_time.timestamp()), UTC
            )
        if self.end_time:
            self.end_time = datetime.fromtimestamp(int(self.end_time.timestamp()), UTC)

    def is_bidding_open(self) -> bool:
        """
        :return: True if the Auction is Committed and the current time is within the bidding session window.
        """
        if self.start_time and self.end_time:
            return (
                self.status == AuctionStatus.COMMITTED
                and self.start_time <= datetime.now(UTC) < self.end_time
            )
        return False

    def is_ended(self) -> bool:
        """
        :return: True if the auction has ended, but not yet fully finalized
        """
        if self.status in [
            AuctionStatus.BID_ACCEPTED,
            AuctionStatus.CANCELLED,
        ]:
            return True

        return (
            self.status == AuctionStatus.COMMITTED
            # if status is committed, then `end_time` is not None
            and datetime.now(UTC) > self.end_time  # type: ignore
        )

    def is_sold(self) -> bool:
        """
        :return: True if the Auction has sold
        """

        if self.status == AuctionStatus.BID_ACCEPTED:
            return True

        return (
            self.status == AuctionStatus.COMMITTED
            # if status is committed, then `end_time` is not None
            and datetime.now(UTC) > self.end_time  # type: ignore
            and self.highest_bid > 0
        )
