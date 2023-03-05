import pprint
import unittest
from datetime import timedelta
from pathlib import Path
from time import sleep

from beaker import sandbox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions
from ulid import ULID

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.lookup_auction import (
    LookupAuction,
)
from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_manager_events import (
    SearchAuctionManagerEvents,
    AuctionManagerEvent,
)
from oysterpack.apps.auction_app.commands.data.algorand_sync.import_auction import (
    ImportAuction,
)
from oysterpack.apps.auction_app.commands.data.algorand_sync.refresh_auctions import (
    RefreshAuctions,
)
from oysterpack.apps.auction_app.commands.data.delete_auctions import DeleteAuctions
from oysterpack.apps.auction_app.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
)
from oysterpack.apps.auction_app.commands.data.queries.lookup_auction_manager import (
    LookupAuctionManager,
)
from oysterpack.apps.auction_app.commands.data.register_auction_manager import (
    RegisterAuctionManager,
)
from oysterpack.apps.auction_app.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction_app.commands.data.unregister_auction_manager import (
    UnregisterAuctionManager,
)
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.apps.auction_app.domain.service_state import (
    SearchAuctionManagerEventsServiceState,
)
from oysterpack.apps.auction_app.services.auction_manager_watcher_service import (
    AuctionManagerWatcherService,
    AuctionManagerWatcherServiceEvent,
)
from tests.algorand.test_support import AlgorandTestCase


class AuctionManagerWatcherServiceTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.setup_database()
        self.setup_contracts()

        import_auction = ImportAuction(
            lookup=LookupAuction(
                self.algod_client,
                LookupAuctionManager(self.session_factory),
            ),
            store=StoreAuctions(self.session_factory),
            delete=DeleteAuctions(self.session_factory),
        )

        self.service = AuctionManagerWatcherService(
            session_factory=self.session_factory,
            get_registered_auction_managers=GetRegisteredAuctionManagers(
                self.session_factory
            ),
            search_auction_manager_events=SearchAuctionManagerEvents(self.indexer),
            refresh_auctions=RefreshAuctions(import_auction),
            poll_interval=timedelta(seconds=1),
        )

    def setup_database(self):
        # in-memory database canot be used here because the import process runs in a separate thread
        db_file = Path(f"{self.__class__.__name__}.sqlite")
        if db_file.exists():
            Path.unlink(db_file)
        self.engine = create_engine(f"sqlite:///{db_file}", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory = sessionmaker(self.engine)

        self.register_auction_manager = RegisterAuctionManager(self.session_factory)

    def setup_contracts(self):
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        self.creator_auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )

        self.register_auction_manager(
            AuctionManagerAppId(self.creator_auction_manager_client.app_id)
        )

        self.seller_auction_manager_client = self.creator_auction_manager_client.copy(
            sender=Address(seller.address),
            signer=seller.signer,
        )

    def tearDown(self) -> None:
        self.service.stop()
        close_all_sessions()

    def test_service_state_read_write(self) -> None:
        auction_manager_app_id = AuctionManagerAppId(
            self.creator_auction_manager_client.app_id
        )

        auction_created_state = SearchAuctionManagerEventsServiceState(
            service_name=self.service.name,
            auction_manager_app_id=auction_manager_app_id,
            event=AuctionManagerEvent.AUCTION_CREATED,
            min_round=10,
            next_token=str(ULID()),
        )

        with self.subTest("when no service state exists in the database"):
            database_state: dict[
                AuctionManagerEvent, SearchAuctionManagerEventsServiceState
            ] = self.service.get_state(auction_manager_app_id)
            self.assertEqual(0, len(database_state))

        with self.subTest("database insert"):
            self.service._save_state(auction_created_state)
            database_state = self.service.get_state(auction_manager_app_id)
            self.assertEqual(
                auction_created_state, database_state[auction_created_state.event]
            )

            auction_deleted_state = SearchAuctionManagerEventsServiceState(
                service_name=self.service.name,
                auction_manager_app_id=auction_manager_app_id,
                event=AuctionManagerEvent.AUCTION_DELETED,
                next_token=str(ULID()),
            )

            self.service._save_state(auction_deleted_state)
            database_state = self.service.get_state(auction_manager_app_id)
            self.assertEqual(2, len(database_state))
            self.assertEqual(
                auction_created_state, database_state[auction_created_state.event]
            )
            self.assertEqual(
                auction_deleted_state, database_state[auction_deleted_state.event]
            )

        with self.subTest("database update"):
            auction_deleted_state.next_token = str(ULID())
            self.service._save_state(auction_deleted_state)
            database_state = self.service.get_state(auction_manager_app_id)
            self.assertEqual(2, len(database_state))
            self.assertEqual(
                auction_created_state, database_state[auction_created_state.event]
            )
            self.assertEqual(
                auction_deleted_state, database_state[auction_deleted_state.event]
            )

        with self.subTest(
            "when auction manager is unregistered, deletes should cascade"
        ):
            UnregisterAuctionManager(self.session_factory)(auction_manager_app_id)

            database_state = self.service.get_state(auction_manager_app_id)
            self.assertEqual(0, len(database_state))

    def test_service(self) -> None:
        events: list[AuctionManagerWatcherServiceEvent] = []

        def on_event(event: AuctionManagerWatcherServiceEvent):
            nonlocal events
            pprint.pp(event)
            events.append(event)

        def get_auction_event_count(evt: AuctionManagerEvent | None = None) -> int:
            if evt is None:
                return sum([len(event.auction_txns) for event in events])
            return sum(
                [len(event.auction_txns) for event in events if event.event == evt]
            )

        self.service.observable.subscribe(on_event)
        self.service.start()

        with self.subTest("initial startup with no Auctions on Algorand"):
            sleep(2)
            self.assertEqual(0, len(events))

        with self.subTest("when auctions have been created on Algorand"):
            app_clients = []
            for _ in range(5):
                app_clients.append(self.seller_auction_manager_client.create_auction())
            sleep(0.5)  # give indexer time to index

            sleep(3)
            self.assertEqual(len(app_clients), get_auction_event_count())

        with self.subTest("when more auctions have been created on Algorand"):
            for _ in range(5):
                app_clients.append(self.seller_auction_manager_client.create_auction())
            sleep(0.5)  # give indexer time to index

            sleep(3)
            self.assertEqual(len(app_clients), get_auction_event_count())

        with self.subTest("when auctions have been deleted on Algorand"):
            for app_client in app_clients[0:5]:
                app_client.cancel()
                app_client.finalize()
                self.creator_auction_manager_client.delete_finalized_auction(
                    app_client.app_id
                )

            sleep(0.5)  # give indexer time to index

            sleep(3)
            self.assertEqual(len(app_clients) + 5, get_auction_event_count())
            self.assertEqual(
                len(app_clients),
                get_auction_event_count(AuctionManagerEvent.AUCTION_CREATED),
            )
            self.assertEqual(
                5, get_auction_event_count(AuctionManagerEvent.AUCTION_DELETED)
            )


if __name__ == "__main__":
    unittest.main()
