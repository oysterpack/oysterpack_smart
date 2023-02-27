"""
Command to insert/update Auctions into the database
"""

from dataclasses import dataclass

from oysterpack.apps.auction_app.commands.data import (
    SqlAlchemySupport,
)
from oysterpack.apps.auction_app.data.auction import TAuction
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.core.command import Command


@dataclass
class StoreAuctionsResult:
    """
    Returns the number of auctions that were
    """

    inserts: int
    updates: int


class StoreAuctions(
    Command[list[Auction], StoreAuctionsResult],
    SqlAlchemySupport,
):
    """
    Stores the auctions in the database.

    The store functions like an upsert.
    If the auction does not exist in the database, then it will be inserted.
    Otherwise, the auction will be updated.
    """

    def __call__(self, auctions: list[Auction]) -> StoreAuctionsResult:
        if len(auctions) == 0:
            return StoreAuctionsResult(inserts=0, updates=0)

        inserts = 0
        updates = 0

        with self._session_factory.begin() as session:
            for auction in auctions:
                existing_auction: TAuction | None = session.get(
                    TAuction, auction.app_id
                )
                if existing_auction:
                    existing_auction.update(auction)
                    updates += 1
                else:
                    session.add(TAuction.create(auction))
                    inserts += 1

        return StoreAuctionsResult(inserts=inserts, updates=updates)
