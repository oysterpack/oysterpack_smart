"""
Provides command to retrieve the max AuctionAppId.
"""
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from oysterpack.apps.auction.data.auction import TAuction
from oysterpack.apps.auction.domain.auction import AuctionManagerAppId, AuctionAppId


class GetMaxAuctionAppId:
    """
    Returns None if no auctions exist in the database for the specified auction manager app ID.
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def __call__(
        self, auction_manager_app_id: AuctionManagerAppId
    ) -> AuctionAppId | None:
        # E1102: func.max is not callable (not-callable)
        # pylint: disable=not-callable

        with self._session_factory() as session:
            return session.scalar(
                select(func.max(TAuction.app_id)).where(
                    TAuction.auction_manager_app_id == auction_manager_app_id
                )
            )
