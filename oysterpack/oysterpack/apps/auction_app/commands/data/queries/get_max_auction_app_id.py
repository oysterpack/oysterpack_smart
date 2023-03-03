"""
Provides command to retrieve the max AuctionAppId.
"""
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from oysterpack.algorand.client.model import AppId
from oysterpack.apps.auction_app.data.auction import TAuction
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId


class GetMaxAuctionAppId:
    """
    Returns None if no auctions exist in the database for the specified auction manager app ID.
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def __call__(self, auction_manager_app_id: AuctionManagerAppId) -> AppId | None:
        # E1102: func.max is not callable (not-callable)
        # pylint: disable=not-callable

        with self._session_factory() as session:
            query = select(func.max(TAuction.app_id)).where(
                TAuction.auction_manager_app_id == auction_manager_app_id
            )
            max_app_id = session.scalar(query)
            if max_app_id is None:
                return None
            return AppId(max_app_id)
