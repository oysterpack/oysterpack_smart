"""
Retrieves an Auction from the database
"""
from oysterpack.apps.auction_app.commands.data import SqlAlchemySupport
from oysterpack.apps.auction_app.data.auction import TAuction
from oysterpack.apps.auction_app.domain.auction import AuctionAppId, Auction
from oysterpack.core.command import Command


class GetAuction(
    Command[AuctionAppId, Auction | None],
    SqlAlchemySupport,
):
    """
    Retrieves Auction from the database by its AppId
    """

    def __call__(self, auction_app_id: AuctionAppId) -> Auction | None:
        with self._session_factory() as session:
            auction = session.get(TAuction, auction_app_id)
            if auction is None:
                return None

            return auction.to_auction()
