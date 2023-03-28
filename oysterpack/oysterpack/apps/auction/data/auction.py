"""
Auction data model
"""
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import cast, Optional

from algosdk.logic import get_application_address
from sqlalchemy import (
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oysterpack.algorand.client.model import AssetId, AppId, Address
from oysterpack.apps.auction.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.domain.auction import Auction
from oysterpack.apps.auction.domain.auction_state import AuctionState


@dataclass
class TAuctionManager(Base):
    """
    AuctionManager database table model.

    Used to store the valid set of AuctionManager app IDs that are supported by the app.
    """

    __tablename__ = "auction_manager"

    app_id: Mapped[AppId] = mapped_column(primary_key=True)
    address: Mapped[Address] = mapped_column(unique=True)

    @classmethod
    def create(cls, app_id: AppId) -> "TAuctionManager":
        """
        :param app_id: AuctionManager AppId
        :return: TAuctionManager
        """
        return TAuctionManager(
            app_id=cast(Mapped[AppId], app_id),
            address=cast(Mapped[Address], get_application_address(app_id)),
        )


class TAuction(Base):
    """
    Auction database table model
    """

    # pylint: disable=too-many-instance-attributes

    __tablename__ = "auction"

    app_id: Mapped[AppId] = mapped_column(primary_key=True)

    # auction creator
    auction_manager_app_id: Mapped[AppId] = mapped_column(
        ForeignKey("auction_manager.app_id"),
        index=True,
    )

    # when the record was last updated in the database
    updated_at: Mapped[int] = mapped_column(index=True)  # epoch time

    status: Mapped[AuctionStatus] = mapped_column(index=True, init=False)
    seller: Mapped[Address] = mapped_column(index=True, init=False)

    bid_asset_id: Mapped[AssetId | None] = mapped_column(index=True, init=False)
    min_bid: Mapped[int | None] = mapped_column(index=True, init=False)

    highest_bidder: Mapped[Address | None] = mapped_column(index=True, init=False)
    highest_bid: Mapped[int] = mapped_column(index=True, init=False)

    start_time: Mapped[int | None] = mapped_column(index=True, init=False)  # epoch time
    end_time: Mapped[int | None] = mapped_column(index=True, init=False)  # epoch time

    assets: Mapped[list["TAuctionAsset"]] = relationship(
        cascade="all, delete-orphan",
        single_parent=True,
        passive_deletes=True,
        lazy="selectin",
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
        tauction = cls(
            app_id=cast(Mapped[AppId], auction.app_id),
            auction_manager_app_id=cast(Mapped[AppId], auction.auction_manager_app_id),
            updated_at=cast(Mapped[int], int(datetime.now(UTC).timestamp())),
            assets=cast(Mapped[list[TAuctionAsset]], assets),
        )
        tauction.state = auction.state
        return tauction

    @property
    def state(self) -> AuctionState:
        """
        :return: AuctionState
        """

        return AuctionState(
            status=cast(AuctionStatus, self.status),
            seller=cast(Address, self.seller),
            bid_asset_id=cast(AssetId, self.bid_asset_id)
            if self.bid_asset_id
            else None,
            min_bid=cast(int, self.min_bid),
            highest_bidder=cast(Address, self.highest_bidder)
            if self.highest_bidder
            else None,
            highest_bid=cast(int, self.highest_bid),
            start_time=datetime.fromtimestamp(cast(int, self.start_time), UTC)
            if self.start_time
            else None,
            end_time=datetime.fromtimestamp(cast(int, self.end_time), UTC)
            if self.end_time
            else None,
        )

    @state.setter
    def state(self, auction_state: AuctionState):
        self.status = cast(Mapped[AuctionStatus], auction_state.status)
        self.seller = cast(Mapped[Address], auction_state.seller)

        self.bid_asset_id = cast(Mapped[AssetId | None], auction_state.bid_asset_id)
        self.min_bid = cast(Mapped[int | None], auction_state.min_bid)

        self.highest_bidder = cast(Mapped[Address | None], auction_state.highest_bidder)
        self.highest_bid = cast(Mapped[int], auction_state.highest_bid)

        self.start_time = cast(
            Mapped[int | None],
            int(auction_state.start_time.timestamp())
            if auction_state.start_time
            else None,
        )
        self.end_time = cast(
            Mapped[int | None],
            int(auction_state.end_time.timestamp()) if auction_state.end_time else None,
        )

    def update(self, auction: Auction):
        """
        Updates the auction with the specified `Auction` data that was retrieved at the specified round

        Notes
        -----
        - `updated_at` timestamp is set to the current EPOCH time
        """

        if self.app_id != auction.app_id:
            raise AssertionError("app_id does not match")

        self.auction_manager_app_id = cast(
            Mapped[AppId], auction.auction_manager_app_id
        )
        self.updated_at = cast(Mapped[int], int(datetime.now(UTC).timestamp()))
        self.state = auction.state

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
            app_id=cast(AppId, self.app_id),
            auction_manager_app_id=cast(AppId, self.auction_manager_app_id),
            state=self.state,
            assets={
                cast(AssetId, asset.asset_id): cast(int, asset.amount)
                for asset in cast(list[TAuctionAsset], self.assets)
            },
        )

    def get_asset(self, asset_id: AssetId) -> Optional["TAuctionAsset"]:
        """
        :return: None if the auction does not hold the asset
        """
        for asset in cast(list[TAuctionAsset], self.assets):
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
            cast(list[TAuctionAsset], self.assets).append(
                TAuctionAsset.create(cast(AppId, self.app_id), asset_id, amount)
            )

    def set_assets(self, assets: dict[AssetId, int]):
        """
        Replaces the existing set of Auction assets with the specified assets.
        """
        auction_assets = [
            TAuctionAsset.create(cast(AppId, self.app_id), asset_id, amount)
            for asset_id, amount in assets.items()
        ]
        self.assets = cast(Mapped[list[TAuctionAsset]], auction_assets)


class TAuctionAsset(Base):
    """
    Auction asset database table model
    """

    __tablename__ = "auction_asset"

    auction_id: Mapped[AppId] = mapped_column(
        ForeignKey("auction.app_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[AssetId] = mapped_column(primary_key=True)
    amount: Mapped[int] = mapped_column(index=True)

    @classmethod
    def create(
        cls,
        auction_id: AppId,
        asset_id: AssetId,
        amount: int,
    ) -> "TAuctionAsset":
        """
        Constructs a TAuctionAsset instance
        """
        return cls(
            auction_id=cast(Mapped[AppId], auction_id),
            asset_id=cast(Mapped[AssetId], asset_id),
            amount=cast(Mapped[int], amount),
        )
