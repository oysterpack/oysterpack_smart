"""
Service State
"""
from dataclasses import dataclass

from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_manager_events import (
    AuctionManagerEvent,
)
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId


@dataclass
class SearchAuctionManagerEventsServiceState:
    """
    SearchAuctionManagerEvents service state
    """

    service_name: str
    auction_manager_app_id: AuctionManagerAppId
    event: AuctionManagerEvent
    min_round: int | None = None
    next_token: str | None = None
