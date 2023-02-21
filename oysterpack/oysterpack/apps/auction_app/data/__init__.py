"""
Auction data model
"""
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus


class Base(DeclarativeBase):
    """
    Data model base class.

    All data model classes should extend Base.
    """

    # pylint: disable=too-few-public-methods

    type_annotation_map = {
        AppId: Integer,
        Address: String(58),
        AssetId: Integer,
        AuctionStatus: Integer,
    }
