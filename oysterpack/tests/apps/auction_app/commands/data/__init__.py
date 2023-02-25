from datetime import datetime, UTC, timedelta

from algosdk.account import generate_account

from oysterpack.algorand.client.model import Address, AssetId, AppId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState


def create_auctions(
    count: int = 100,
    seller: Address | None = None,
    bid_asset_id: AssetId | None = None,
    min_bid: int = 100,
    highest_bidder: Address | None = None,
    highest_bid: int | None = None,
    auction_app_id_start_at: int = 1,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    _private_key, creator = generate_account()

    if seller is None:
        _private_key, seller = generate_account()

    _private_key, bidder = generate_account()

    if highest_bidder is None:
        _private_key, highest_bidder = generate_account()

    bid_asset_id = AssetId(10) if bid_asset_id is None else bid_asset_id

    if highest_bid is None:
        highest_bid = 1000

    if start_time is None:
        start_time = datetime.now(UTC)

    if end_time is None:
        end_time = start_time + timedelta(days=1)

    states = [
        AuctionState(
            status=AuctionStatus.NEW,
            seller=Address(seller),
        ),
        AuctionState(
            status=AuctionStatus.COMMITTED,
            seller=Address(seller),
            bid_asset_id=bid_asset_id,
            min_bid=min_bid,
            highest_bidder=None,
            highest_bid=0,
            start_time=start_time,
            end_time=end_time,
        ),
        AuctionState(
            status=AuctionStatus.BID_ACCEPTED,
            seller=Address(seller),
            bid_asset_id=bid_asset_id,
            min_bid=min_bid,
            highest_bidder=Address(highest_bidder),
            highest_bid=highest_bid,
            start_time=start_time,
            end_time=end_time,
        ),
        AuctionState(
            status=AuctionStatus.FINALIZED,
            seller=Address(seller),
            bid_asset_id=bid_asset_id,
            min_bid=min_bid,
            highest_bidder=Address(highest_bidder),
            highest_bid=highest_bid,
            start_time=start_time,
            end_time=end_time,
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
        for i in range(auction_app_id_start_at, auction_app_id_start_at + count)
    ]
