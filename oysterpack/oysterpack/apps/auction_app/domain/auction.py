"""
Auction domain model
"""

from dataclasses import dataclass

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.client.auction_client import AuctionState


@dataclass(slots=True)
class Auction:
    """
    Auction
    """

    # pylint: disable=too-many-instance-attributes

    app_id: AppId
    creator: Address
    created_at_round: int
    # the round (Algorand block) from which the data was retrieved
    round: int

    state: AuctionState
    assets: dict[AssetId, int]
