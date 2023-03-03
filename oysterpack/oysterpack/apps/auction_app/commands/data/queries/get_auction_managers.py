"""
Used to retrieve the list of registered AuctionManager apps from the database
"""
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.data.auction import TAuctionManager
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId

RegisteredAuctionManagers = list[Tuple[AuctionManagerAppId, Address]]


class GetRegisteredAuctionManagers:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def __call__(self) -> RegisteredAuctionManagers:
        with self._session_factory() as session:
            return [
                (auction_manager.app_id, auction_manager.address)
                for auction_manager in session.scalars(select(TAuctionManager))
            ]
