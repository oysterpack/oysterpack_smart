"""
Asset Info data model
"""

from sqlalchemy.orm import Mapped, mapped_column

from oysterpack.algorand.client.model import AssetId, Address
from oysterpack.apps.auction_app.data import Base


class TAssetInfo(Base):
    """
    Asset info database table model
    """

    __tablename__ = "asset_info"

    asset_id: Mapped[AssetId] = mapped_column(primary_key=True)
    creator: Mapped[Address] = mapped_column(index=True)

    total: Mapped[int] = mapped_column(index=True)
    decimals: Mapped[int] = mapped_column(index=True)

    default_frozen: Mapped[bool | None] = mapped_column(index=True, default=None)
    unit_name: Mapped[str | None] = mapped_column(index=True, default=None)
    asset_name: Mapped[str | None] = mapped_column(index=True, default=None)

    manager: Mapped[Address | None] = mapped_column(index=True, default=None)
    reserve: Mapped[Address | None] = mapped_column(index=True, default=None)
    freeze: Mapped[Address | None] = mapped_column(index=True, default=None)
    clawback: Mapped[Address | None] = mapped_column(index=True, default=None)

    url: Mapped[str | None] = mapped_column(default=None)
    metadata_hash: Mapped[str | None] = mapped_column(default=None)
