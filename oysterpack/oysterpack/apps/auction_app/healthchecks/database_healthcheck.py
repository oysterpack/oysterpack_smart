"""
Auction database healthcheck
"""
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from oysterpack.apps.auction_app.data.asset_info import TAssetInfo
from oysterpack.apps.auction_app.data.auction import (
    TAuction,
    TAuctionManager,
    TAuctionAsset,
)
from oysterpack.core.health_check import HealthCheck, HealthCheckImpact


class DatabaseHealthCheck(HealthCheck):
    def __init__(self, session_factory: sessionmaker):
        super().__init__(
            name="auction_database",
            impact=HealthCheckImpact.HIGH,
            description="Queries each of the auction database tables",
            tags={"database"},
        )

        self.__session_factory = session_factory

    def execute(self):
        with self.__session_factory() as session:
            session.scalar(select(TAuctionManager).limit(1))
            session.scalar(select(TAuction).limit(1))
            session.scalar(select(TAuctionAsset).limit(1))
            session.scalar(select(TAssetInfo).limit(1))
