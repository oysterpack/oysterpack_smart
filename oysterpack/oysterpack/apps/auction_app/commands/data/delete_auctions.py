from sqlalchemy import delete

from oysterpack.algorand.client.model import AppId
from oysterpack.apps.auction_app.commands.data.SqlAlchemySupport import (
    SqlAlchemySupport,
)
from oysterpack.apps.auction_app.data.auction import TAuction
from oysterpack.core.command import Command


class DeleteAuctions(
    Command[list[AppId], None],
    SqlAlchemySupport,
):
    """
    Deletes auctions from the database for the specified auction app IDs.

    Returns the number of records that were deleted.
    """

    def __call__(self, auction_app_ids: list[AppId]):
        with self.session_factory.begin() as session:
            session.execute(
                delete(TAuction).where(TAuction.app_id.in_(auction_app_ids))
            )
