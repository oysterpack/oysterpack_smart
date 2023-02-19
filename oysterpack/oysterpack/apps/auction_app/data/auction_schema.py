"""
Auction database schema
"""

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from oysterpack.algorand.client.model import AppId, Address


class Base(DeclarativeBase):
    pass


class Auction(Base):
    __tablename__ = "auction"

    app_id: Mapped[AppId] = mapped_column(primary_key=True)

    creator: Mapped[Address] = mapped_column(String(58), nullable=False, index=True)

    created_at_round: Mapped[int] = mapped_column(index=True)


metadata = MetaData()

auction = Table(
    "auction",
    metadata,
    Column("app_id", Integer, primary_key=True),
    Column("creator_address", String(58), nullable=False, index=True),
    Column("created_at_round", Integer, nullable=False, index=True),
    Column("created_at_time", Integer, nullable=False, index=True),
    Column("status", Integer, nullable=False, index=True),
    Column("seller_address", String(58), nullable=False, index=True),
    Column("bid_asset_id", Integer, index=True),
    Column("min_bid", Integer, index=True),
    Column("highest_bidder_address", String(58), index=True),
    Column("highest_bid", Integer, index=True),
    Column("start_time", Integer, index=True),
    Column("end_time", Integer, index=True),
)

asset_holding = Table(
    "asset_holding",
    metadata,
    Column(
        "app_id",
        ForeignKey("auction.app_id"),
        nullable=False,
        index=True,
    ),
    Column("asset_id", Integer, nullable=False, index=True),
    Column("amount", Integer, nullable=False, index=True),
)
