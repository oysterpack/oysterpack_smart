"""
Provides service that polls Algorand for new Auctions to import into the database
"""
from datetime import timedelta
from threading import Thread
from time import sleep

from reactivex import Observable, Subject
from reactivex.operators import observe_on

from oysterpack.apps.auction_app.commands.data.algorand_sync.import_auctions import (
    ImportAuctions,
    ImportAuctionsRequest,
)
from oysterpack.apps.auction_app.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
)
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.core.logging import get_logger
from oysterpack.core.rx import default_scheduler
from oysterpack.core.service import Service, ServiceCommand


class AuctionImportService(Service):
    """
    Launches a background thread that polls Algorand for new Auctions for each registered AuctionManager.
    """

    def __init__(
        self,
        import_auctions: ImportAuctions,
        get_auction_managers: GetRegisteredAuctionManagers,
        commands: Observable[ServiceCommand] | None = None,
        poll_interval: timedelta = timedelta(seconds=3),
    ):
        super().__init__(commands)
        self._import_auctions = import_auctions
        self._get_auction_managers = get_auction_managers
        self._poll_interval = poll_interval

        self._subject: Subject[list[Auction]] = Subject()
        self._observable: Observable[list[Auction]] = self._subject.pipe(
            observe_on(default_scheduler)
        )

    @property
    def imported_auctions_observable(self) -> Observable[list[Auction]]:
        """
        Imported auctions are published to this stream
        """
        return self._observable

    def _start(self):
        logger = get_logger(self)

        def _run_import():
            logger.info("import thread is running")
            while not self._stopped_event.is_set():
                auction_managers = self._get_auction_managers()

                for auction_manager in auction_managers:
                    request = ImportAuctionsRequest(
                        auction_manager_app_id=auction_manager.app_id
                    )
                    auctions = self._import_auctions(request)
                    logger.info(
                        "[%s] auction import count = %s",
                        auction_manager.app_id,
                        len(auctions),
                    )
                    if len(auctions) > 0:
                        self._subject.on_next(auctions)
                    else:
                        if self._stopped_event.is_set():
                            logger.info("stop signalled - import thread is exiting")
                            return
                sleep(self._poll_interval.seconds)

            logger.info("stop signalled - import thread is exiting")

        Thread(
            target=_run_import,
            name=self.__class__.__name__,
            daemon=True,
        ).start()
