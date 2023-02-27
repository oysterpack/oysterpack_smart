"""
Lookup an auction manager record by app ID or address
"""
from typing import Tuple

from sqlalchemy import select

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.commands.data import SqlAlchemySupport
from oysterpack.apps.auction_app.data.auction import TAuctionManager
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.core.command import Command


class LookupAuctionManager(
    Command[AuctionManagerAppId | Address, Tuple[AuctionManagerAppId, Address] | None],
    SqlAlchemySupport,
):
    """
    Looks up the auction manager either by app ID or app address.

    Returns None, if the auction manager does not exist in the database
    """

    def __call__(
            self, id: AuctionManagerAppId | Address
    ) -> Tuple[AuctionManagerAppId, Address] | None:
        with self._session_factory() as session:
            if isinstance(id, int):
                auction_manager: TAuctionManager | None = session.get(TAuctionManager, id)
            elif isinstance(id, str):
                auction_manager = session.scalar(
                    select(TAuctionManager).where(TAuctionManager.address == id)
                )
            else:
                raise ValueError("id type must be: AuctionManagerAppId | Address")

            if auction_manager is None:
                return None
            return AuctionManagerAppId(auction_manager.app_id), auction_manager.address
