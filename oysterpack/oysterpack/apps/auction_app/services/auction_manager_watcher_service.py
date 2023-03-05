"""
Polls Algorand for AuctionManager related transactions that create/delete auctions
and updates the database accordingly.
"""
from dataclasses import dataclass
from datetime import timedelta
from threading import Thread
from time import sleep

from reactivex import Observable, Subject
from reactivex.operators import observe_on
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_manager_events import (
    SearchAuctionManagerEvents,
    AuctionManagerEvent,
    SearchAuctionManagerEventsRequest,
    Transaction,
)
from oysterpack.apps.auction_app.commands.data.algorand_sync.refresh_auctions import (
    RefreshAuctions,
)
from oysterpack.apps.auction_app.commands.data.queries.get_auction_managers import (
    GetRegisteredAuctionManagers,
)
from oysterpack.apps.auction_app.data.service_state import TSearchAuctionManagerEvents
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId, AuctionAppId
from oysterpack.apps.auction_app.domain.service_state import (
    SearchAuctionManagerEventsServiceState,
)
from oysterpack.core.logging import get_logger
from oysterpack.core.rx import default_scheduler
from oysterpack.core.service import Service, ServiceCommand


@dataclass(slots=True)
class AuctionManagerWatcherServiceEvent:
    auction_manager_app_id: AuctionManagerAppId
    event: AuctionManagerEvent
    auction_txn_ids: dict[AuctionAppId, Transaction]


class AuctionManagerWatcherService(Service):
    def __init__(
        self,
        session_factory: sessionmaker,
        get_registered_auction_managers: GetRegisteredAuctionManagers,
        search_auction_manager_events: SearchAuctionManagerEvents,
        refresh_auctions: RefreshAuctions,
        poll_interval: timedelta = timedelta(seconds=3),
        batch_size: int = 100,
        commands: Observable[ServiceCommand] | None = None,
    ):
        super().__init__(commands)

        self._session_factory = session_factory
        self._get_registered_auction_managers = get_registered_auction_managers
        self._search_auction_manager_events = search_auction_manager_events
        self._refresh_auctions = refresh_auctions
        self._poll_interval = poll_interval
        self._batch_size = batch_size

        # init observable
        self._subject: Subject[AuctionManagerWatcherServiceEvent] = Subject()
        self._observable: Observable[
            AuctionManagerWatcherServiceEvent
        ] = self._subject.pipe(observe_on(default_scheduler))

    @property
    def observable(self) -> Observable[AuctionManagerWatcherServiceEvent]:
        return self._observable

    def _start(self):
        """
        Steps
        -----
        1. get list of registered auction managers
        2. for each registered auction manager spawn a thread to monitor events
        3. Handle each event accordingly
        4. Publish the events to an Observable stream
        """

        logger = get_logger(self)

        def run() -> None:
            logger.info("running")
            while not self._stopped_event.is_set():
                has_more_results = False
                for (
                    registered_auction_manager
                ) in self._get_registered_auction_managers():
                    for event in [
                        AuctionManagerEvent.AUCTION_DELETED,
                        AuctionManagerEvent.AUCTION_CREATED,
                    ]:
                        if self._stopped_event.is_set():
                            logger.info("stop signalled - exiting")
                            return

                        state = self.get_state(registered_auction_manager.app_id)
                        min_round = state[event].min_round if event in state else None
                        next_token = state[event].next_token if event in state else None
                        result = self._search_auction_manager_events(
                            SearchAuctionManagerEventsRequest(
                                auction_manager_app_id=registered_auction_manager.app_id,
                                event=event,
                                min_round=min_round,
                                limit=self._batch_size,
                                next_token=next_token,
                            )
                        )

                        if not has_more_results:
                            has_more_results = result.next_token is not None
                        logger.debug(
                            "has_more_results=%s, next_token=%s, min_round=%s",
                            has_more_results,
                            result.next_token,
                            min_round,
                        )

                        if result.auction_txns and len(result.auction_txns) > 0:
                            self._refresh_auctions(list(result.auction_txns.keys()))
                            self._subject.on_next(
                                AuctionManagerWatcherServiceEvent(
                                    registered_auction_manager.app_id,
                                    event,
                                    result.auction_txns,
                                )
                            )
                            max_confirmed_round = max(
                                [
                                    txn.confirmed_round
                                    for txn in result.auction_txns.values()
                                ]
                            )
                            self._save_state(
                                SearchAuctionManagerEventsServiceState(
                                    service_name=self.name,
                                    auction_manager_app_id=registered_auction_manager.app_id,
                                    event=event,
                                    min_round=max_confirmed_round,
                                    next_token=result.next_token,
                                )
                            )
                    if not has_more_results:
                        logger.debug("sleeping")
                        sleep(self._poll_interval.seconds)

            logger.info("stop signalled - exiting")

        Thread(target=run, name=self.name, daemon=True).start()

    def get_state(
        self,
        auction_manager_app_id: AuctionManagerAppId,
    ) -> dict[AuctionManagerEvent, SearchAuctionManagerEventsServiceState]:
        """
        Looks up service state in the database
        """
        query = select(TSearchAuctionManagerEvents).where(
            TSearchAuctionManagerEvents.auction_manager_app_id == auction_manager_app_id
        )
        with self._session_factory() as session:
            rs = session.scalars(query)
            return {state.event: state.to_domain_object() for state in rs}

    def _save_state(self, state: SearchAuctionManagerEventsServiceState):
        """
        Store service state in the database
        """
        with self._session_factory.begin() as session:
            existing_state: TSearchAuctionManagerEvents | None = session.get(
                TSearchAuctionManagerEvents,
                (self.name, state.auction_manager_app_id, state.event),
            )

            if existing_state:
                existing_state.next_token = state.next_token
                existing_state.min_round = state.min_round
            else:
                session.add(TSearchAuctionManagerEvents.create(state))
