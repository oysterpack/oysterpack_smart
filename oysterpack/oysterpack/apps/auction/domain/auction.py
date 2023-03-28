"""
Auction domain model
"""

from dataclasses import dataclass
from typing import NewType

from algosdk.logic import get_application_address

from oysterpack.algorand.client.model import AppId, AssetId, Address
from oysterpack.apps.auction.client.auction_client import AuctionState

AuctionManagerAppId = NewType("AuctionManagerAppId", AppId)

AuctionAppId = NewType("AuctionAppId", AppId)


@dataclass(slots=True)
class Auction:
    """
    Auction
    """

    # pylint: disable=too-many-instance-attributes

    app_id: AppId

    # auction creator
    auction_manager_app_id: AppId

    state: AuctionState
    assets: dict[AssetId, int]

    @property
    def auction_manager_app_address(self) -> Address:
        """
        :return: AuctionManager application address that corresponds to its app ID
        """
        return Address(get_application_address(self.auction_manager_app_id))
