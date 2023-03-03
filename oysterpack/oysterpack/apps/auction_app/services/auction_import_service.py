"""
Provides service that polls Algorand for new Auctions to import into the database
"""

from reactivex import Observable

from oysterpack.apps.auction_app.commands.data.algorand_sync.import_auctions import (
    ImportAuctions,
)
from oysterpack.core.service import Service, ServiceCommand


class AuctionImportService(Service):
    def __init__(
        self,
        import_auctions: ImportAuctions,
        commands: Observable[ServiceCommand] | None = None,
    ):
        super().__init__(commands)
        self._import_auctions = import_auctions

    def _start(self):
        def _run_import():
            while not self._stopped_event.is_set():
                pass
