"""
Algorand node health check
"""
from dataclasses import dataclass

from algosdk.v2client.algod import AlgodClient

from oysterpack.core.health_check import HealthCheck, HealthCheckImpact, RedHealthCheck


@dataclass(slots=True)
class AlgorandNodeNotCaughtUp(RedHealthCheck):
    catchup_time: int


class AlgorandNodeHealthCheck(HealthCheck):
    """
    Algorand node health check
    """

    def __init__(self, algod_client: AlgodClient):
        super().__init__(
            name="algorand_node",
            impact=HealthCheckImpact.HIGH,
            description=[
                "Checks that the algod client can connect to the node."
                "Checks that the node is caught up with the rest of the blockchain."
            ],
            tags={"algorand", "algod"},
        )

        self.__algod_client = algod_client

    def execute(self):
        result = self.__algod_client.status()
        if catchup_time := result["catchup-time"] > 0:
            raise AlgorandNodeNotCaughtUp(catchup_time)
