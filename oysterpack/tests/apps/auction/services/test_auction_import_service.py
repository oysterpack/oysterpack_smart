import unittest
from pathlib import Path
from time import sleep

from reactivex import Subject
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction.client.auction_manager_client import (
    create_auction_manager,
)
from oysterpack.apps.auction.commands.auction_algorand_search.search_auctions import (
    SearchAuctions,
)
from oysterpack.apps.auction.commands.data.algorand_sync.import_auctions import (
    ImportAuctions,
)
from oysterpack.apps.auction.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
)
from oysterpack.apps.auction.commands.data.queries.get_max_auction_app_id import (
    GetMaxAuctionAppId,
)
from oysterpack.apps.auction.commands.data.register_auction_manager import (
    RegisterAuctionManager,
)
from oysterpack.apps.auction.commands.data.store_auctions import StoreAuctions
from oysterpack.apps.auction.data import Base
from oysterpack.apps.auction.domain.auction import AuctionManagerAppId, Auction
from oysterpack.apps.auction.services.auction_import_service import (
    AuctionImportService,
)
from oysterpack.core.service import ServiceCommand
from tests.algorand.test_support import AlgorandTestCase


class AuctionImportServiceTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.setup_database()
        self.setup_contracts()

        commands_subject: Subject[ServiceCommand] = Subject()

        import_auctions = ImportAuctions(
            search=SearchAuctions(
                indexer_client=self.indexer,
                algod_client=self.algod_client,
            ),
            store=self.store_auctions,
            get_max_auction_app_id=self.get_max_auction_app_id,
        )
        self.auction_import_service = AuctionImportService(
            import_auctions=import_auctions,
            get_auction_managers=GetRegisteredAuctionManagers(self.session_factory),
            commands=commands_subject,
        )

    def setup_database(self):
        # in-memory database canot be used here because the import process runs in a separate thread
        db_file = Path(f"{self.__class__.__name__}.sqlite")
        if db_file.exists():
            Path.unlink(db_file)
        self.engine = create_engine(f"sqlite:///{db_file}", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory = sessionmaker(self.engine)
        self.store_auctions = StoreAuctions(self.session_factory)
        self.get_max_auction_app_id = GetMaxAuctionAppId(self.session_factory)
        self.register_auction_manager = RegisterAuctionManager(self.session_factory)

    def setup_contracts(self):
        accounts = self.get_sandbox_accounts()
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

        self.app_ids = []
        for _ in range(5):
            self.app_ids.append(
                self.seller_auction_manager_client.create_auction().app_id
            )
        sleep(1)

    def tearDown(self) -> None:
        self.auction_import_service.stop()
        close_all_sessions()

    def test_import(self) -> None:
        imported_auctions: list[Auction] = []

        def on_next(auctions: list[Auction]):
            nonlocal imported_auctions
            imported_auctions += auctions

        self.auction_import_service.imported_auctions_observable.subscribe(on_next)
        self.auction_import_service.start()

        # give some time for the import process to run
        sleep(5)

        self.assertEqual(len(self.app_ids), len(imported_auctions))


if __name__ == "__main__":
    unittest.main()
