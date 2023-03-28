"""
HealthCheck errors
"""
from dataclasses import dataclass

from oysterpack.apps.auction.domain.auction import AuctionManagerAppId
from oysterpack.core.health_check import YellowHealthCheck


@dataclass
class AuctionManagerAppLookupFailed(YellowHealthCheck):
    """
    Indicates the indexer is running, but failed to find the AuctionManager application.

    This is flagged as yellow because the indexer may be lagging or the contract has been deleted on the blockchain
    but is still registered in the database.
    """

    auction_manager_app_id: AuctionManagerAppId
