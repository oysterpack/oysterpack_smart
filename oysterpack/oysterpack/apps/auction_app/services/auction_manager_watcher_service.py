"""
Polls Algorand for AuctionManager related transactions that create and delete auctions.
"""
from dataclasses import dataclass
from datetime import timedelta
from threading import Thread
from time import sleep
from typing import Iterable, Tuple

from reactivex import Observable, Subject
from reactivex.operators import observe_on
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_manager_events import (
    SearchAuctionManagerEvents,
    AuctionManagerEvent,
    SearchAuctionManagerEventsRequest,
    Transaction,
    SearchAuctionManagerEventsResult,
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

MinRound = int | None
NextToken = str | None


@dataclass(slots=True)
class AuctionManagerWatcherServiceEvent:
    """
    AuctionManagerWatcherServiceEvent
    """

    auction_manager_app_id: AuctionManagerAppId
    event: AuctionManagerEvent
    auction_txns: dict[AuctionAppId, Transaction]


class AuctionManagerWatcherService(Service):
    """
    Monitors Algorand for auctions that are created or deleted for registered auction managers, and then:
    1. updates the database accordingly
    2. publishes events (AuctionManagerWatcherServiceEvent) to an Observable stream

    Notes
    -----
    - service runs in a background thread
    - AuctionImportService` is also designed to monitor Algorand for new Auctions to import into the database.
      Thus, there is some work overlap between the 2 services. If both services are running, then this service
      can be configured to only monitor Algorand for transactions that delete auctions.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(
        self,
        session_factory: sessionmaker,
        get_registered_auction_managers: GetRegisteredAuctionManagers,
        search_auction_manager_events: SearchAuctionManagerEvents,
        refresh_auctions: RefreshAuctions,
        poll_interval: timedelta = timedelta(seconds=3),
        events_watched: Iterable[AuctionManagerEvent] = (
            AuctionManagerEvent.AUCTION_DELETED,
            AuctionManagerEvent.AUCTION_CREATED,
        ),
        batch_size: int = 100,
        commands: Observable[ServiceCommand] | None = None,
    ):
        super().__init__(commands)

        self._session_factory = session_factory
        self._get_registered_auction_managers = get_registered_auction_managers
        self._search_auction_manager_events = search_auction_manager_events
        self._refresh_auctions = refresh_auctions
        self._poll_interval = poll_interval
        self._events_watched = set(events_watched)
        self._batch_size = batch_size

        if len(self._events_watched) == 0:
            raise ValueError("at least 1 AuctionManagerEvent is required")

        # init observable
        self._subject: Subject[AuctionManagerWatcherServiceEvent] = Subject()
        self._observable: Observable[
            AuctionManagerWatcherServiceEvent
        ] = self._subject.pipe(observe_on(default_scheduler))

    @property
    def events_watched(self) -> list[AuctionManagerEvent]:
        """
        :return: list[AuctionManagerEvent] that are being watched for`
        """
        return list(self._events_watched)

    @property
    def observable(self) -> Observable[AuctionManagerWatcherServiceEvent]:
        """
        :return: Observable[AuctionManagerWatcherServiceEvent]
        """
        return self._observable

    def _start(self):
        """
        For each registered AuctionManager:
        1. Search for Auctions that have been created and deleted since the last search.
        2. Retrieve SearchAuctionManagerEvents request params from the database to continue from the last search.
        3. Process each Auction create/delete event by importing/deleting the auctions in the database.
        4. Save the search result next-token and the confirmed round for the event transaction.
        5. Publish events (AuctionManagerWatcherServiceEvent) on the Observable stream
        """

        logger = get_logger(self)

        def get_request_params(
            auction_manager_app_id: AuctionManagerAppId,
            event: AuctionManagerEvent,
        ) -> Tuple[MinRound, NextToken]:
            state = self.get_state(auction_manager_app_id)
            return (
                (state[event].min_round, state[event].next_token)
                if event in state
                else (None, None)
            )

        def search_auction_manager_events(
            auction_manager_app_id: AuctionManagerAppId,
            event: AuctionManagerEvent,
            min_round: MinRound,
            next_token: NextToken,
        ) -> SearchAuctionManagerEventsResult:
            return self._search_auction_manager_events(
                SearchAuctionManagerEventsRequest(
                    auction_manager_app_id=auction_manager_app_id,
                    event=event,
                    min_round=min_round,
                    next_token=next_token,
                    limit=self._batch_size,
                )
            )

        def publish_event(
            auction_manager_app_id: AuctionManagerAppId,
            event: AuctionManagerEvent,
            auction_txns: dict[AuctionAppId, Transaction],
        ):
            self._subject.on_next(
                AuctionManagerWatcherServiceEvent(
                    auction_manager_app_id,
                    event,
                    auction_txns,
                )
            )

        def save_search_params(
            auction_manager_app_id: AuctionManagerAppId,
            event: AuctionManagerEvent,
            txns: Iterable[Transaction],
            next_token: NextToken,
        ):
            max_confirmed_round = max((txn.confirmed_round for txn in txns))
            self._save_state(
                SearchAuctionManagerEventsServiceState(
                    service_name=self.name,
                    auction_manager_app_id=auction_manager_app_id,
                    event=event,
                    min_round=max_confirmed_round,
                    next_token=next_token,
                )
            )

        def run() -> None:
            logger.info("running")
            while not self._stopped_event.is_set():
                has_more_results = False
                for (
                    registered_auction_manager
                ) in self._get_registered_auction_managers():
                    for event in self._events_watched:
                        if self._stopped_event.is_set():
                            logger.info("stop signalled - exiting")
                            return

                        min_round, next_token = get_request_params(
                            registered_auction_manager.app_id, event
                        )
                        result = search_auction_manager_events(
                            auction_manager_app_id=registered_auction_manager.app_id,
                            event=event,
                            min_round=min_round,
                            next_token=next_token,
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
                            publish_event(
                                registered_auction_manager.app_id,
                                event,
                                result.auction_txns,
                            )
                            save_search_params(
                                auction_manager_app_id=registered_auction_manager.app_id,
                                event=event,
                                txns=result.auction_txns.values(),
                                next_token=result.next_token,
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
            query_results = session.scalars(query)
            return {state.event: state.to_domain_object() for state in query_results}

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
