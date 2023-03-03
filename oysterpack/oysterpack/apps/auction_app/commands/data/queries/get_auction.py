"""
Retrieves an Auction from the database
"""
from sqlalchemy.orm import sessionmaker

from oysterpack.apps.auction_app.data.auction import TAuction
from oysterpack.apps.auction_app.domain.auction import AuctionAppId, Auction


class GetAuction:
    """
    Retrieves Auction from the database by its AppId
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def __call__(self, auction_app_id: AuctionAppId) -> Auction | None:
        with self._session_factory() as session:
            auction = session.get(TAuction, auction_app_id)
            if auction is None:
                return None

            return auction.to_auction()
