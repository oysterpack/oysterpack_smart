"""
Auction database schema
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    String,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus


class Base(DeclarativeBase):
    pass


@dataclass
class Auction(Base):
    __tablename__ = "auction"

    app_id: Mapped[int] = mapped_column(primary_key=True)
    creator: Mapped[str] = mapped_column(String(58), index=True)
    created_at_round: Mapped[int] = mapped_column(index=True)

    status: Mapped[AuctionStatus] = mapped_column(index=True)
    seller: Mapped[str] = mapped_column(String(58), index=True)

    bid_asset_id: Mapped[int | None] = mapped_column(index=True)
    min_bid: Mapped[int | None] = mapped_column(index=True)

    highest_bidder: Mapped[str | None] = mapped_column(String(58), index=True)
    highest_bid: Mapped[int] = mapped_column(index=True)

    start_time: Mapped[datetime | None] = mapped_column(index=True)
    end_time: Mapped[datetime | None] = mapped_column(index=True)

    assets: Mapped[list["AuctionAsset"]] = relationship()


@dataclass
class AuctionAsset(Base):
    __tablename__ = "auction_asset"

    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auction.app_id"), primary_key=True
    )
    asset_id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[int] = mapped_column(index=True)
