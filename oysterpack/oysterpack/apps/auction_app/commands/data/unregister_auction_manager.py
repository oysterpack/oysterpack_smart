"""
Unregisters an AuctionManager
"""

from sqlalchemy import delete

from oysterpack.apps.auction_app.commands.data import SqlAlchemySupport
from oysterpack.apps.auction_app.data.auction import TAuctionManager, TAuction
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.core.command import Command


class UnregisterAuctionManager(
    Command[AuctionManagerAppId, None],
    SqlAlchemySupport,
):
    """
    Unregistering an AuctionManager will cascade delete all associated Auctions.
    """

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
