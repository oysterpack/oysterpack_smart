"""
Auction domain model
"""

from dataclasses import dataclass
from typing import NewType

from algosdk.logic import get_application_address

from oysterpack.algorand.client.model import AppId, AssetId, Address
from oysterpack.apps.auction_app.client.auction_client import AuctionState

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
    created_at_round: int
    # the round (Algorand block) from which the data was retrieved
    round: int

    state: AuctionState
    assets: dict[AssetId, int]

    @property
    def auction_manager_app_address(self) -> Address:
        return Address(get_application_address(self.auction_manager_app_id))
