"""
Algorand Indexer HealthCheck
"""
from dataclasses import dataclass

from algosdk.error import IndexerHTTPError
from algosdk.v2client.indexer import IndexerClient

from oysterpack.apps.auction_app.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
)
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.core.health_check import (
    HealthCheck,
    HealthCheckImpact,
    YellowHealthCheck,
)


@dataclass
class AuctionManagerAppLookupFailed(YellowHealthCheck):
    """
    Indicates the indexer is running, but failed to find the AuctionManager application.

    This is flagged as yellow because the indexer may be lagging or the contract has been deleted on the blockchain
    but is still registered in the database.
    """

    auction_manager_app_id: AuctionManagerAppId


class AlgorandIndexerHealthCheck(HealthCheck):
    """
    Algorand Indexer HealthCheck
    """

    def __init__(
        self,
        indexer_client: IndexerClient,
        get_auction_managers: GetRegisteredAuctionManagers,
    ):
        super().__init__(
            name="algorand_indexer",
            impact=HealthCheckImpact.HIGH,
            description=[
                "Retrieve the first block from the Indexer",
                "Lookup the application for each registered AuctionManager",
            ],
            tags={"algorand", "indexer"},
        )

        self.__indexer_client = indexer_client
        self.__get_auction_managers = get_auction_managers

    def execute(self):
        self.__indexer_client.block_info(1)
        for auction_manager in self.__get_auction_managers():
            try:
                self.__indexer_client.applications(auction_manager.app_id)
            except IndexerHTTPError as err:
                raise AuctionManagerAppLookupFailed(auction_manager.app_id) from err
