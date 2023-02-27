from datetime import datetime, UTC, timedelta
from typing import cast

from algosdk.account import generate_account
from algosdk.logic import get_application_address
from sqlalchemy.orm import sessionmaker, Mapped

from oysterpack.algorand.client.model import Address, AssetId, AppId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data.auction import TAuctionManager
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState


def store_auction_manager_app_id(session_factory: sessionmaker, app_id: AppId):
    with session_factory.begin() as session:
        auction_manager = session.get(TAuctionManager, app_id)
        if auction_manager is None:
            session.add(
                TAuctionManager(
                    cast(Mapped[AppId], app_id),
                    cast(Mapped[Address], get_application_address(app_id)),
                )
            )


def create_auctions(
    count: int = 100,
    auction_app_id_start_at: int = 1,
    auction_manager_app_id: AppId | None = None,
    seller: Address | None = None,
    bid_asset_id: AssetId | None = None,
    min_bid: int = 100,
    highest_bidder: Address | None = None,
    highest_bid: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    assets: dict[AssetId, int] | None = None,
):
    if auction_manager_app_id is None:
        auction_manager_app_id = AppId(5555)

    if seller is None:
        _private_key, seller = generate_account()

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
            auction_manager_app_id=auction_manager_app_id,
            state=states[i % 5],
            assets={
                AssetId(i): i,
                AssetId(i + 1): i + 1,
                AssetId(i + 2): i + 2,
            }
            if assets is None
            else assets,
        )
        for i in range(auction_app_id_start_at, auction_app_id_start_at + count)
    ]
