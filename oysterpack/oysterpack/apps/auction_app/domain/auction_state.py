"""
Auction application state
"""

from dataclasses import dataclass
from datetime import datetime, UTC

from oysterpack.algorand.client.model import Address, AssetId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus


@dataclass(slots=True)
class AuctionState:
    """
    Auction application contract state
    """

    # pylint: disable=too-many-instance-attributes

    status: AuctionStatus
    seller_address: Address

    bid_asset_id: AssetId | None
    min_bid: int | None

    highest_bidder_address: Address | None
    highest_bid: int

    start_time: datetime | None
    end_time: datetime | None

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
