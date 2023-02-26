from typing import NewType

from sqlalchemy import select, func

from oysterpack.algorand.client.model import AppId
from oysterpack.apps.auction_app.commands.data import SqlAlchemySupport
from oysterpack.apps.auction_app.data.auction import TAuction
from oysterpack.core.command import Command

AuctionManagerAppId = NewType("AuctionManagerAppId", AppId)


class GetMaxAuctionAppId(Command[AuctionManagerAppId, AppId | None], SqlAlchemySupport):
    """
    Returns None if no auctions exist in the database for the specified auction manager app ID.
    """

    def __call__(self, auction_manager_app_id: AuctionManagerAppId) -> AppId | None:
        # E1102: func.max is not callable (not-callable)
        # pylint: disable=not-callable

        with self.session_factory() as session:
            query = select(func.max(TAuction.app_id)).where(
                TAuction.auction_manager_app_id == auction_manager_app_id
            )
            max_app_id = session.scalar(query)
            if max_app_id is None:
                return None
            return AppId(max_app_id)
