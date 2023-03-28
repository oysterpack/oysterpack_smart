"""
Registers an AuctionManager in the database
"""
from typing import cast

from algosdk.logic import get_application_address
from sqlalchemy.orm import Mapped, sessionmaker

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.apps.auction.data.auction import TAuctionManager
from oysterpack.apps.auction.domain.auction import AuctionManagerAppId


class RegisterAuctionManager:
    """
    Registers the AuctionManager in the database
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def __call__(self, auction_manager_app_id: AuctionManagerAppId):
        with self._session_factory.begin() as session:
            auction_manager = session.get(TAuctionManager, auction_manager_app_id)
            if auction_manager is None:
                session.add(
                    TAuctionManager(
                        cast(Mapped[AppId], auction_manager_app_id),
                        cast(
                            Mapped[Address],
                            get_application_address(auction_manager_app_id),
                        ),
                    )
                )
