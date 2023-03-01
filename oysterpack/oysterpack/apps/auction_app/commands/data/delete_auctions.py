"""
Command to delete auctions from the database
"""

from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from oysterpack.algorand.client.model import AppId
from oysterpack.apps.auction_app.data.auction import TAuction
from oysterpack.core.command import Command


class DeleteAuctions(Command[list[AppId], None]):
    """
    Deletes auctions from the database for the specified auction app IDs.

    Returns the number of records that were deleted.
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def __call__(self, auction_app_ids: list[AppId]):
        with self._session_factory.begin() as session:
            session.execute(
                delete(TAuction).where(TAuction.app_id.in_(auction_app_ids))
            )
