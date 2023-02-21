"""
Auction data model
"""
from copy import copy
from datetime import datetime, UTC
from typing import cast, Optional

from sqlalchemy import (
    String,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, composite

from oysterpack.algorand.client.model import AssetId, AppId, Address
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.apps.auction_app.domain.auction_state import AuctionState


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
    updated_at: Mapped[datetime] = mapped_column(index=True)
    # Algorand round at which the data was retrieved
    updated_at_round: Mapped[int] = mapped_column(index=True)

    state: Mapped[AuctionState] = composite(
        mapped_column(index=True),  # status
        mapped_column(index=True),  # seller
        mapped_column(  # bid_asset_id
            ForeignKey("asset_info.asset_id"),
            index=True,
        ),
        mapped_column(index=True),  # min_bid
        mapped_column(index=True),  # highest_bidder
        mapped_column(index=True),  # highest_bid
        mapped_column(index=True),  # start_time
        mapped_column(index=True),  # end_time
        default=None,
    )

    assets: Mapped[list["TAuctionAsset"]] = relationship(
        back_populates="auction",
        cascade="all, delete-orphan",
        default_factory=list,
    )

    @classmethod
    def create(cls, auction: Auction) -> "TAuction":
        """
        Converts Auction -> TAuction

        The `round` is when the snapshot of the on-chain data was taken.
        """
        assets = [
            TAuctionAsset.create(auction.app_id, asset_id, amount)
            for asset_id, amount in auction.assets.items()
        ]
        return cls(
            app_id=auction.app_id,
            creator=auction.creator,
            created_at_round=auction.created_at_round,
            updated_at=datetime.now(UTC),
            updated_at_round=auction.round,
            state=copy(auction.state),
            assets=assets,
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
        self.updated_at = cast(Mapped[datetime], datetime.now(UTC))
        self.updated_at_round = cast(Mapped[int], auction.round)
        self.state = cast(Mapped[AuctionState],copy(auction.state))

        self.assets = cast(
            Mapped[list[TAuctionAsset]],
            [
                TAuctionAsset.create(auction.app_id, asset_id, amount)
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
            round=self.updated_at_round,
            state=self.state,
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
            self.assets.append(TAuctionAsset.create(self.app_id, asset_id, amount))

    def set_assets(self, assets: dict[AssetId, int]):
        """
        Replaces the existing set of Auction assets with the specified assets.
        """
        auction_assets = [
            TAuctionAsset.create(self.app_id, asset_id, amount)
            for asset_id, amount in assets.items()
        ]
        self.assets = cast(Mapped[list[TAuctionAsset]], auction_assets)


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

    auction: Mapped["TAuction"] = relationship(back_populates="assets", default=None)

    @classmethod
    def create(
        cls, auction_id: AppId, asset_id: AssetId, amount: int
    ) -> "TAuctionAsset":
        """
        Constructs a TAuctionAsset instance
        """
        return cls(
            auction_id=auction_id,
            asset_id=asset_id,
            amount=amount,
        )
