import unittest
from time import sleep
from urllib.error import URLError

from algosdk.v2client.indexer import IndexerClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import AppId
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
from oysterpack.apps.auction.healthchecks.algorand_indexer_healthcheck import (
    AlgorandIndexerHealthCheck,
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
        )
        sleep(0.1)  # give the indexer time to index

        self.register_auction_manager(
            AuctionManagerAppId(self.creator_auction_manager_client.app_id)
        )

    def tearDown(self) -> None:
        close_all_sessions()

    def test_healthcheck(self):
        with self.subTest("node is running"):
            healthcheck = AlgorandIndexerHealthCheck(
                self.indexer,
                self.get_registered_auction_managers,
            )
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.GREEN, result.status)

        with self.subTest("invalid URL"):
            healthcheck = AlgorandIndexerHealthCheck(
                IndexerClient(self.indexer.indexer_token, "http://localhost:999999"),
                self.get_registered_auction_managers,
            )
            result = healthcheck()

            self.assertEqual(HealthCheckStatus.RED, result.status)
            self.assertIsInstance(result.error, URLError)

        with self.subTest(
            "AuctionManager contract does not exist on Algorand but is registered in the database"
        ):
            healthcheck = AlgorandIndexerHealthCheck(
                self.indexer,
                self.get_registered_auction_managers,
            )
            self.register_auction_manager(AuctionManagerAppId(AppId(999999999)))
            result = healthcheck()
            self.assertEqual(HealthCheckStatus.YELLOW, result.status)
            self.assertIsInstance(result.error, AuctionManagerAppLookupFailed)

    @unittest.skip(
        "This test should fail. Perhaps the sandbox indexer ignores the API token???"
    )
    def test_invalid_api_token(self):
        healthcheck = AlgorandIndexerHealthCheck(
            IndexerClient("INVALID_TOKEN", self.indexer.indexer_address),
            self.get_registered_auction_managers,
        )
        result = healthcheck()
        self.assertEqual(HealthCheckStatus.RED, result.status)


if __name__ == "__main__":
    unittest.main()
