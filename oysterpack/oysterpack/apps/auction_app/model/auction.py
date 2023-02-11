from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, auto

from oysterpack.algorand.client.model import AppId, Address, AssetId


class AuctionStatus(IntEnum):
    """
    An auction starts out in the `New` state, and terminates in the `Finalized` state.

    Valid state transitions
    -----------------------
    New -> Initialized

    Committed -> Started
    Committed -> Cancelled

    Started -> BidAccepted
    Started -> Sold
    Started -> NotSold

    Sold -> Finalized
    NotSold -> Finalized
    Cancelled -> Finalized
    """

    New = auto()
    # Once the auction is committed, its settings can no longer be changed
    # A committed auction can transition to the Cancelled or Started states
    Committed = auto()
    # Seller can cancel the auction as long it has not started.
    # Once the auction has been started, it cannot be cancelled.
    Cancelled = auto()

    # Seller accepted the highest bid and has ended the auction.
    BidAccepted = auto()

    # All assets have transferred out of the contracts.
    #
    # If status == Sold, then:
    # 1. payment is transferred from the buyer's escrow account to the seller
    # 2. assets are transferred from the seller's escrow to the
    Finalized = auto()

    def __repr__(self) -> str:
        match (self):
            case AuctionStatus.New:
                return f"New({AuctionStatus.New.value})"
            case AuctionStatus.Committed:
                return f"Committed({AuctionStatus.Committed.value})"
            case AuctionStatus.Cancelled:
                return f"Cancelled({AuctionStatus.Cancelled.value})"
            case AuctionStatus.BidAccepted:
                return f"BidAccepted({AuctionStatus.BidAccepted.value})"
            case AuctionStatus.Finalized:
                return f"Finalized({AuctionStatus.Finalized.value})"


@dataclass(slots=True)
class Bid:
    """
    The bid payment is made in USD stablecoin(s).
    The auction may accept multiple USD stablecoins as payment.
    Each stablecoin is valued at $1.
    """

    buyer: Address
    payment: dict[AssetId, int]


@dataclass(slots=True)
class Auction:
    seller: Address
    status: AuctionStatus

    # application escrow contract that holds the seller's assets
    # the types of assets being auctioned are determined by the contract's asset holdings
    seller_escrow_id: AppId
    # application escrow contract that holds the buyer's bid payment
    # the types of accepted payment are determined by the contract's asset holdings
    buyer_escrow_id: AppId

    # the first bid must be at least match the min bid
    min_bid: int | None
    # to place a new high bid, it must be at least greater than this amount
    # new_bid >= current_highest_bid + min_bid _raise
    min_bid_raise: int | None

    # times are in UTC
    # When the auction starts. The start time can be future dated.
    # The start time can only be set when status == Initialized
    start_time: datetime | None
    # When the auction bidding session ends. Bids will be rejected if submitted after the end_time.
    end_time: datetime | None

    highest_bid: Bid | None
