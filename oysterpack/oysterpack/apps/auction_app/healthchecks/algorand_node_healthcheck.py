"""
Algorand node health check
"""
from dataclasses import dataclass

from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient

from oysterpack.apps.auction_app.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
)
from oysterpack.apps.auction_app.healthchecks.errors import (
    AuctionManagerAppLookupFailed,
)
from oysterpack.core.health_check import HealthCheck, HealthCheckImpact, RedHealthCheck


@dataclass(slots=True)
class AlgorandNodeNotCaughtUp(RedHealthCheck):
    """
    Indicates the node is in catchup mode.
    While in catchup mode, transactions will not be accepted, i.e., submitting transactions will fail.
    """

    catchup_time: int


class AlgorandNodeHealthCheck(HealthCheck):
    """
    Algorand node health check
    """

    def __init__(
        self,
        algod_client: AlgodClient,
        get_auction_managers: GetRegisteredAuctionManagers,
    ):
        super().__init__(
            name="algorand_node",
            impact=HealthCheckImpact.HIGH,
            description=[
                "Checks that the node is caught up with the rest of the blockchain.",
                "Looks up the application for each registered AuctionManager",
            ],
            tags={"algorand", "algod"},
        )

        self.__algod_client = algod_client
        self.__get_auction_managers = get_auction_managers

    def execute(self):
        result = self.__algod_client.status()
        if catchup_time := result["catchup-time"] > 0:
            raise AlgorandNodeNotCaughtUp(catchup_time)

        for auction_manager in self.__get_auction_managers():
            try:
                self.__algod_client.application_info(auction_manager.app_id)
            except AlgodHTTPError as err:
                if err.code == 404:
                    raise AuctionManagerAppLookupFailed(auction_manager.app_id) from err
                raise err
