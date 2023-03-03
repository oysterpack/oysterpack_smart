"""
Unregisters an AuctionManager
"""

from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from oysterpack.apps.auction_app.data.auction import TAuctionManager, TAuction
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId


class UnregisterAuctionManager:
    """
    Unregistering an AuctionManager will cascade delete all associated Auctions.
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def __call__(self, auction_manager_app_id: AuctionManagerAppId):
        with self._session_factory.begin() as session:
            auction_manager = session.get(TAuctionManager, auction_manager_app_id)
            if auction_manager is not None:
                session.execute(
                    delete(TAuction).where(
                        TAuction.auction_manager_app_id == auction_manager_app_id
                    )
                )
                session.delete(auction_manager)
