import logging
import unittest
from dataclasses import dataclass, field
from datetime import timedelta
from time import sleep

from reactivex import Observer

from oysterpack.core.health_check import HealthCheck, HealthCheckImpact
from oysterpack.core.service import (
    Service,
    ServiceLifecycleEvent,
)
from oysterpack.core.service_manager import ServiceManager
from tests.test_support import OysterPackTestCase

logger = logging.getLogger("ServiceTestCase")


class FooHealthCheck(HealthCheck):
    def __init__(self, name: str = "foo"):
        super().__init__(
            name=name,
            impact=HealthCheckImpact.HIGH,
            description="Foo health check",
            tags={"database"},
            run_interval=timedelta(seconds=1),
        )

    def execute(self):
        logger.info("executing FooHealthCheck")


class FooService(Service):
    start_error: Exception | None = None
    stop_error: Exception | None = None

    def _start(self):
        if self.start_error is not None:
            raise self.start_error

        self._healthchecks = [FooHealthCheck(), FooHealthCheck("bar")]

    def _stop(self):
        if self.stop_error is not None:
            raise self.stop_error


class BarService(Service):
    start_error: Exception | None = None
    stop_error: Exception | None = None

    def _start(self):
        if self.start_error is not None:
            raise self.start_error

        self._healthchecks = [FooHealthCheck(), FooHealthCheck("bar")]

    def _stop(self):
        if self.stop_error is not None:
            raise self.stop_error


@dataclass
class ServiceStateSubscriber(Observer[ServiceLifecycleEvent]):
    events_received: list[ServiceLifecycleEvent] = field(default_factory=list)
    event: ServiceLifecycleEvent | None = None
    error: Exception | None = None
    completed: bool = False

    def on_next(self, event: ServiceLifecycleEvent) -> None:
        logger.info(f"ServiceStateSubscriber.on_next(): {event}")
        self.event = event
        self.events_received.append(event)

    def on_error(self, error: Exception) -> None:
        logger.info(f"ServiceStateSubscriber.on_error(): {error}")
        self.error = error

    def on_completed(self) -> None:
        logger.info("ServiceStateSubscriber.on_completed()")
        self.completed = True


class ServiceTestCase(OysterPackTestCase):
    def test_service_lifecycle(self):
        service_manager = ServiceManager([FooService(), BarService()])

        # subscribe to service state events
        service_state_observer = ServiceStateSubscriber()
        service_manager.service_lifecycle_event_observable.subscribe(
            service_state_observer
        )
        # signal the service to start
        service_manager.start()

        service_manager.await_running()

        for service in service_manager.services:
            self.assertTrue(service.running)

        # healthcheck is scheduled to run every second
        # sleep for 2 seconds to give time to run heatlh checks
        sleep(3)

        service_manager.stop()

        service_manager.await_stopped()

        for service in service_manager.services:
            self.assertTrue(service.stopped)


if __name__ == "__main__":
    unittest.main()
