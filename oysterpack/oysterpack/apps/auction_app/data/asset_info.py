from dataclasses import dataclass

from sqlalchemy.orm import Mapped, mapped_column

from oysterpack.apps.auction_app.data import Base


@dataclass
class AssetInfo(Base):
    """
    Asset info
    """

    __tablename__ = "asset_info"

    asset_id: Mapped[int] = mapped_column(primary_key=True)
