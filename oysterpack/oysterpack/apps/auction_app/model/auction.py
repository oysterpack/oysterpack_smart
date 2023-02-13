from enum import IntEnum, auto


class AuctionStatus(IntEnum):
    """
    When an auction is created, it starts out in the `New` state
    The auction's final state is `Finalized`.

    - When the seller is done setting up the auction, then the seller commits the auction.
    - An auction can only be cancelled while in the `New` state.
    - Once the seller is done setting up the auction, then the seller commits the auction.
    - Once the auction is committed, its settings are frozen and awaits the bidding session to start.
    - The seller can accept a bid during the bidding session before the bidding session's end time.
      This effectively ends the auction early.
    - When the auction is cancelled or after the bidding session completes, the auction needs to be finalized.
    - During the finalization phase, assets are closed out on the auction
      - If the auction was cancelled, then all assets are closed out to the seller.
      - If the auction sold, then auction assets are closed out to the highest bidder, and the bid payment asset
        is closed out to the seller.
    """

    New = auto()
    Committed = auto()
    Cancelled = auto()
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
