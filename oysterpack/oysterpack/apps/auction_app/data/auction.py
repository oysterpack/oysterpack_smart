"""
Auction data model
"""
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


class TAuction(Base):
    """
    Auction database table model
    """

    # pylint: disable=too-many-instance-attributes

    __tablename__ = "auction"

    app_id: Mapped[AppId] = mapped_column(primary_key=True)

    # auction creator
    auction_manager_app_id: Mapped[AppId] = mapped_column(String(58), index=True)
    created_at_round: Mapped[int] = mapped_column(index=True)

    # when the record was last updated
    updated_at: Mapped[int] = mapped_column(index=True)  # epoch time
    # Algorand round at which the data was retrieved
    updated_at_round: Mapped[int] = mapped_column(index=True)

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
            app_id=auction.app_id,
            auction_manager_app_id=auction.auction_manager_app_id,
            created_at_round=auction.created_at_round,
            updated_at=int(datetime.now(UTC).timestamp()),
            updated_at_round=auction.round,
            assets=assets,
        )
        tauction.state = auction.state
        return tauction

    @property
    def state(self) -> AuctionState:
        """
        :return: AuctionState
        """

        return AuctionState(
            status=AuctionStatus(self.status),
            seller=Address(self.seller),
            bid_asset_id=AssetId(self.bid_asset_id) if self.bid_asset_id else None,
            min_bid=self.min_bid,
            highest_bidder=Address(self.highest_bidder)
            if self.highest_bidder
            else None,
            highest_bid=self.highest_bid,
            start_time=datetime.fromtimestamp(self.start_time, UTC)
            if self.start_time
            else None,
            end_time=datetime.fromtimestamp(self.end_time, UTC)
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
        self.created_at_round = cast(Mapped[int], auction.created_at_round)
        self.updated_at = cast(Mapped[int], int(datetime.now(UTC).timestamp()))
        self.updated_at_round = cast(Mapped[int], auction.round)
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
            app_id=AppId(self.app_id),
            auction_manager_app_id=AppId(self.auction_manager_app_id),
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
            auction_id=auction_id,
            asset_id=asset_id,
            amount=amount,
        )
