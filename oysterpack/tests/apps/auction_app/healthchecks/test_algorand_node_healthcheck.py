import unittest
from urllib.error import URLError

from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient

from oysterpack.apps.auction_app.healthchecks.algorand_node_healthcheck import (
    AlgorandNodeHealthCheck,
    AlgorandNodeNotCaughtUp,
)
from oysterpack.core.health_check import HealthCheckStatus
from tests.algorand.test_support import AlgorandTestCase


class AlgorandNodeHealthCheckTestCase(AlgorandTestCase):
    def test_healthcheck(self):
        with self.subTest("node is running"):
            healthcheck = AlgorandNodeHealthCheck(self.algod_client)
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.GREEN, result.status)

        with self.subTest("invalid API token"):
            healthcheck = AlgorandNodeHealthCheck(
                AlgodClient("INVALID_TOKEN", "http://localhost:8080")
            )
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.RED, result.status)
            self.assertIsInstance(result.error, AlgodHTTPError)
            self.assertEqual(401, result.error.code)

        with self.subTest("invalid URL"):
            healthcheck = AlgorandNodeHealthCheck(
                AlgodClient("INVALID_TOKEN", "http://localhost:999999")
            )
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.RED, result.status)
            self.assertIsInstance(result.error, URLError)

        with self.subTest("node not caught up"):

            class AlgodClientMock(AlgodClient):
                def status(self, **kwargs):
                    return {"catchup-time": 1}

            healthcheck = AlgorandNodeHealthCheck(
                AlgodClientMock(
                    self.algod_client.algod_token, self.algod_client.algod_address
                )
            )
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.RED, result.status)
            self.assertIsInstance(result.error, AlgorandNodeNotCaughtUp)
            self.assertEqual(1, result.error.catchup_time)


if __name__ == "__main__":
    unittest.main()
