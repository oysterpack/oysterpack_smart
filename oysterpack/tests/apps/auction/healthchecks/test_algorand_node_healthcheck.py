import unittest
from time import sleep
from urllib.error import URLError

from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.apps.auction.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
)
from oysterpack.apps.auction.commands.data.register_auction_manager import (
    RegisterAuctionManager,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.domain.auction import AuctionManagerAppId
from oysterpack.apps.auction.healthchecks.algorand_node_healthcheck import (
    AlgorandNodeHealthCheck,
    AlgorandNodeNotCaughtUp,
)
from oysterpack.apps.auction.healthchecks.errors import (
    AuctionManagerAppLookupFailed,
)
from oysterpack.core.health_check import HealthCheckStatus
from tests.algorand.test_support import AlgorandTestCase


class AlgorandNodeHealthCheckTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory: sessionmaker = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.register_auction_manager = RegisterAuctionManager(self.session_factory)
        self.get_registered_auction_managers = GetRegisteredAuctionManagers(
            self.session_factory
        )

        self.setup_contracts()

    def setup_contracts(self):
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()

        self.creator_auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
            creator=Address(creator.address),
        )
        sleep(0.1)  # give the indexer time to index

        self.register_auction_manager(
            AuctionManagerAppId(self.creator_auction_manager_client.app_id)
        )

    def tearDown(self) -> None:
        close_all_sessions()

    def test_healthcheck(self):
        with self.subTest("node is running"):
            healthcheck = AlgorandNodeHealthCheck(
                self.algod_client,
                self.get_registered_auction_managers,
            )
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.GREEN, result.status)

        with self.subTest("invalid API token"):
            healthcheck = AlgorandNodeHealthCheck(
                AlgodClient("INVALID_TOKEN", self.algod_client.algod_address),
                self.get_registered_auction_managers,
            )
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.RED, result.status)
            self.assertIsInstance(result.error, AlgodHTTPError)
            self.assertEqual(401, result.error.code)

        with self.subTest("invalid URL"):
            healthcheck = AlgorandNodeHealthCheck(
                AlgodClient("INVALID_TOKEN", "http://localhost:999999"),
                self.get_registered_auction_managers,
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
                ),
                self.get_registered_auction_managers,
            )
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.RED, result.status)
            self.assertIsInstance(result.error, AlgorandNodeNotCaughtUp)
            self.assertEqual(1, result.error.catchup_time)

        with self.subTest(
            "AuctionManager contract does not exist on Algorand but is registered in the database"
        ):
            healthcheck = AlgorandNodeHealthCheck(
                self.algod_client,
                self.get_registered_auction_managers,
            )
            self.register_auction_manager(AuctionManagerAppId(AppId(999999999)))
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.YELLOW, result.status)
            self.assertIsInstance(result.error, AuctionManagerAppLookupFailed)


if __name__ == "__main__":
    unittest.main()
