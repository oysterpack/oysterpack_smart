"""
Auction data model
"""
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import cast, Optional

from sqlalchemy import (
    String,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oysterpack.algorand.client.model import AssetId, AppId, Address
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState


@dataclass
class TAuction(Base):
    """
    Auction database table model
    """

    # pylint: disable=too-many-instance-attributes

    __tablename__ = "auction"

    app_id: Mapped[AppId] = mapped_column(primary_key=True)
    creator: Mapped[Address] = mapped_column(String(58), index=True)
    created_at_round: Mapped[int] = mapped_column(index=True)

    # when the record was last updated
    updated_on: Mapped[datetime] = mapped_column(index=True)
    # Algorand round at which the data was retrieved
    round: Mapped[int] = mapped_column(index=True)

    status: Mapped[AuctionStatus] = mapped_column(index=True)
    seller: Mapped[Address] = mapped_column(index=True)

    bid_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_info.asset_id"),
        index=True,
    )
    min_bid: Mapped[int | None] = mapped_column(index=True)

    highest_bidder: Mapped[Address | None] = mapped_column(index=True)
    highest_bid: Mapped[int] = mapped_column(index=True)

    start_time: Mapped[datetime | None] = mapped_column(index=True)
    end_time: Mapped[datetime | None] = mapped_column(index=True)

    assets: Mapped[list["TAuctionAsset"]] = relationship(
        back_populates="auction",
        cascade="all, delete-orphan",
    )

    @classmethod
    def create(cls, auction: Auction) -> "TAuction":
        """
        Converts Auction -> TAuction

        The `round` is when the snapshot of the on-chain data was taken.
        """
        assets = [
            TAuctionAsset.create(asset_id, amount)
            for asset_id, amount in auction.assets.items()
        ]
        return cls(
            app_id=cast(Mapped[AppId], auction.app_id),
            creator=cast(Mapped[Address], auction.creator),
            created_at_round=cast(Mapped[int], auction.created_at_round),
            updated_on=cast(Mapped[datetime], datetime.now(UTC)),
            round=cast(Mapped[int], auction.round),
            status=cast(Mapped[AuctionStatus], auction.state.status),
            seller=cast(Mapped[Address], auction.state.seller),
            bid_asset_id=cast(Mapped[int | None], auction.state.bid_asset_id),
            highest_bidder=cast(Mapped[Address | None], auction.state.highest_bidder),
            highest_bid=cast(Mapped[int], auction.state.highest_bid),
            start_time=cast(Mapped[datetime | None], auction.state.start_time),
            end_time=cast(Mapped[datetime | None], auction.state.end_time),
            assets=cast(Mapped[list[TAuctionAsset]], assets),
        )

    def update(self, auction: Auction):
        """
        Updates the auction with the specified `Auction` data that was retrieved at the specified round
        :param auction:
        :param round:
        :return:
        """

        if self.app_id != auction.app_id:
            raise AssertionError("app_id does not match")

        self.creator = cast(Mapped[Address], auction.creator)
        self.created_at_round = cast(Mapped[int], auction.created_at_round)
        self.updated_on = cast(Mapped[datetime], datetime.now(UTC))
        self.created_at_round = cast(Mapped[int], auction.round)
        self.status = cast(Mapped[AuctionStatus], auction.state.status)
        self.seller = cast(Mapped[Address], auction.state.seller)
        self.bid_asset_id = cast(Mapped[int | None], auction.state.bid_asset_id)
        self.highest_bidder = cast(Mapped[Address | None], auction.state.highest_bidder)
        self.highest_bid = cast(Mapped[int], auction.state.highest_bid)
        self.start_time = cast(Mapped[datetime | None], auction.state.start_time)
        self.end_time = cast(Mapped[datetime | None], auction.state.end_time)
        self.assets = cast(
            Mapped[list[TAuctionAsset]],
            [
                TAuctionAsset.create(asset_id, amount)
                for asset_id, amount in auction.assets.items()
            ],
        )

    def to_auction(self) -> Auction:
        """
        Converts this instance into an Auction instance
        """
        return Auction(
            app_id=AppId(self.app_id),
            creator=Address(self.creator),
            created_at_round=self.created_at_round,
            round=self.round,
            state=AuctionState(
                status=AuctionStatus(self.status),
                seller=Address(self.seller),
                bid_asset_id=cast(AssetId | None, self.bid_asset_id),
                highest_bidder=cast(Address | None, self.highest_bidder),
                highest_bid=self.highest_bid,
                start_time=cast(datetime | None, self.start_time),
                end_time=cast(datetime | None, self.end_time),
            ),
            assets={asset.asset_id: asset.amount for asset in self.assets},
        )

    def get_asset(self, asset_id: AssetId) -> Optional["TAuctionAsset"]:
        """
        :return: None if the auction does not hold the asset
        """
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None

    def set_asset(self, asset_id: AssetId, amount: int) -> None:
        """
        If the Auction does not hold the asset, then it is added.
        Otherwise, its amount is updated.
        """
        asset = self.get_asset(asset_id)
        if asset:
            asset.amount = amount
        else:
            self.assets.append(TAuctionAsset.create(asset_id, amount))

    def set_assets(self, assets: dict[AssetId, int]):
        """
        Replaces the existing set of Auction assets with the specified assets.
        """
        auction_assets = [
            TAuctionAsset.create(asset_id, amount)
            for asset_id, amount in assets.items()
        ]
        self.assets = cast(Mapped[list[TAuctionAsset]], auction_assets)


@dataclass
class TAuctionAsset(Base):
    """
    Auction asset database table model
    """

    __tablename__ = "auction_asset"

    auction_id: Mapped[AppId] = mapped_column(
        ForeignKey("auction.app_id"),
        primary_key=True,
    )
    asset_id: Mapped[AssetId] = mapped_column(
        ForeignKey("asset_info.asset_id"),
        primary_key=True,
    )
    amount: Mapped[int] = mapped_column(index=True)

    auction: Mapped["TAuction"] = relationship(back_populates="assets")

    @classmethod
    def create(cls, asset_id: AssetId, amount: int) -> "TAuctionAsset":
        """
        Constructs a TAuctionAsset instance
        """
        return cls(
            asset_id=cast(Mapped[AssetId], asset_id),
            amount=cast(Mapped[int], amount),
        )
