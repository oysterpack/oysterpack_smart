"""
Auction data model

Notes
-----
Data model class names are prefixed with a 'T', which identifies them as classes that map to database tables.
This naming convention also avoids name collision with other similarly named domain model classes, e.g.,

`TAuction` is a data model class vs `Auction` is a domain model class

"""

from sqlalchemy import Integer, String, event, Engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_manager_events import (
    AuctionManagerEvent,
)
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId, AuctionAppId


class Base(MappedAsDataclass, DeclarativeBase):
    """
    Data model base class.

    All data model classes should extend Base.
    """

    # pylint: disable=too-few-public-methods

    type_annotation_map = {
        AppId: Integer,
        AuctionManagerAppId: Integer,
        AuctionAppId: Integer,
        Address: String(58),
        AssetId: Integer,
        AuctionStatus: Integer,
        AuctionManagerEvent: Integer,
    }


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """
    Enables foreign keys in sqlite
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
