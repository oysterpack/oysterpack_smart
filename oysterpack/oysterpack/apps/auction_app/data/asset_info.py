"""
Asset Info data model
"""

from dataclasses import dataclass

from sqlalchemy.orm import Mapped, mapped_column

from oysterpack.algorand.client.model import AssetId, Address
from oysterpack.apps.auction_app.data import Base


@dataclass
class TAssetInfo(Base):
    """
    Asset info database table model
    """

    __tablename__ = "asset_info"

    asset_id: Mapped[AssetId] = mapped_column(primary_key=True)
    creator: Mapped[Address] = mapped_column(index=True)

    total: Mapped[int] = mapped_column(index=True)
    decimals: Mapped[int] = mapped_column(index=True)

    default_frozen: Mapped[bool | None] = mapped_column(index=True)
    unit_name: Mapped[str | None] = mapped_column(index=True)
    asset_name: Mapped[str | None] = mapped_column(index=True)

    manager: Mapped[Address | None] = mapped_column(index=True)
    reserve: Mapped[Address | None] = mapped_column(index=True)
    freeze: Mapped[Address | None] = mapped_column(index=True)
    clawback: Mapped[Address | None] = mapped_column(index=True)

    url: Mapped[str | None] = mapped_column()
    metadata_hash: Mapped[str | None] = mapped_column()
