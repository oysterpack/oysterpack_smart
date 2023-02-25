from datetime import datetime, UTC, timedelta

from algosdk.account import generate_account

from oysterpack.algorand.client.model import Address, AssetId, AppId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState


def create_auctions(count: int = 100, seller: Address | None = None):
    _private_key, creator = generate_account()
    if seller is None:
        _private_key, seller = generate_account()
    _private_key, bidder = generate_account()

    states = [
        AuctionState(
            status=AuctionStatus.NEW,
            seller=Address(seller),
        ),
        AuctionState(
            status=AuctionStatus.COMMITTED,
            seller=Address(seller),
            bid_asset_id=AssetId(10),
            min_bid=100,
            highest_bidder=None,
            highest_bid=0,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=1),
        ),
        AuctionState(
            status=AuctionStatus.BID_ACCEPTED,
            seller=Address(seller),
            bid_asset_id=AssetId(10),
            min_bid=100,
            highest_bidder=Address(bidder),
            highest_bid=1000,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=1),
        ),
        AuctionState(
            status=AuctionStatus.FINALIZED,
            seller=Address(seller),
            bid_asset_id=AssetId(10),
            min_bid=100,
            highest_bidder=Address(bidder),
            highest_bid=1000,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=1),
        ),
        AuctionState(
            status=AuctionStatus.CANCELLED,
            seller=Address(seller),
        ),
    ]

    return [
        Auction(
            app_id=AppId(i),
            creator=Address(creator),
            created_at_round=i + 1,
            round=i + 2,
            state=states[i % 5],
            assets={
                AssetId(i): i,
                AssetId(i + 1): i + 1,
                AssetId(i + 2): i + 2,
            },
        )
        for i in range(1, count + 1)
    ]
