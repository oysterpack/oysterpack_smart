"""
Auction table
"""
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import cast, Optional

from sqlalchemy import (
    String,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oysterpack.algorand.client.model import AssetId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import Auction as AuctionDomainObject


@dataclass
class Auction(Base):
    """
    Auction
    """

    __tablename__ = "auction"

    app_id: Mapped[int] = mapped_column(primary_key=True)
    creator: Mapped[str] = mapped_column(String(58), index=True)
    created_at_round: Mapped[int] = mapped_column(index=True)

    # when the record was last updated
    updated_on: Mapped[datetime] = mapped_column(index=True)
    # Algorand round at which the data was fetched to insert/update the record
    updated_at_round: Mapped[int] = mapped_column(index=True)

    status: Mapped[AuctionStatus] = mapped_column(index=True)
    seller: Mapped[str] = mapped_column(String(58), index=True)

    bid_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_info.asset_id"),
        index=True,
    )
    min_bid: Mapped[int | None] = mapped_column(index=True)

    highest_bidder: Mapped[str | None] = mapped_column(String(58), index=True)
    highest_bid: Mapped[int] = mapped_column(index=True)

    start_time: Mapped[datetime | None] = mapped_column(index=True)
    end_time: Mapped[datetime | None] = mapped_column(index=True)

    assets: Mapped[list["AuctionAsset"]] = relationship(
        back_populates="auction", cascade="all, delete-orphan"
    )

    @classmethod
    def create(cls, auction: AuctionDomainObject, updated_at_round: int) -> "Auction":
        assets = [
            AuctionAsset.create(asset_id, amount)
            for asset_id, amount in auction.assets.items()
        ]
        return cls(
            app_id=cast(Mapped[int], auction.app_id),
            creator=cast(Mapped[str], auction.creator),
            created_at_round=cast(Mapped[int], auction.created_at_round),
            updated_on=cast(Mapped[datetime], datetime.now(UTC)),
            updated_at_round=cast(Mapped[int], updated_at_round),
            status=cast(Mapped[AuctionStatus], auction.state.status),
            seller=cast(Mapped[str], auction.state.seller),
            bid_asset_id=cast(Mapped[int | None], auction.state.bid_asset_id),
            highest_bidder=cast(Mapped[str | None], auction.state.highest_bidder),
            highest_bid=cast(Mapped[int], auction.state.highest_bid),
            start_time=cast(Mapped[datetime | None], auction.state.start_time),
            end_time=cast(Mapped[datetime | None], auction.state.end_time),
            assets=cast(Mapped[list[AuctionAsset]], assets),
        )

    def get_asset(self, asset_id: AssetId) -> Optional["AuctionAsset"]:
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None

    def add_update_asset(self, asset_id: AssetId, amount: int) -> None:
        asset = self.get_asset(asset_id)
        if asset:
            asset.amount = amount
        else:
            self.assets.append(AuctionAsset.create(asset_id, amount))

    def update_assets(self, assets: dict[AssetId, int]):
        auction_assets = [
            AuctionAsset.create(asset_id, amount) for asset_id, amount in assets.items()
        ]
        self.assets = cast(Mapped[list[AuctionAsset]], auction_assets)


@dataclass
class AuctionAsset(Base):
    """
    Auction asset
    """

    __tablename__ = "auction_asset"

    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auction.app_id"),
        primary_key=True,
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("asset_info.asset_id"),
        primary_key=True,
    )
    amount: Mapped[int] = mapped_column(index=True)

    auction: Mapped["Auction"] = relationship(back_populates="assets")

    @classmethod
    def create(cls, asset_id: AssetId, amount: int) -> "AuctionAsset":
        return cls(
            asset_id=cast(Mapped[int], asset_id),
            amount=cast(Mapped[int], amount),
        )
