import logging
import unittest
from dataclasses import dataclass, field
from datetime import timedelta
from time import sleep

from reactivex import Subject, Observer
from reactivex.operators import observe_on

from oysterpack.core.health_check import HealthCheck, HealthCheckImpact
from oysterpack.core.rx import default_scheduler
from oysterpack.core.service import (
    Service,
    ServiceCommand,
    ServiceStateEvent,
    ServiceState,
    ServiceStartError,
    ServiceStopError,
)
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
        if self.start_error:
            raise self.start_error

        self._healthchecks = [FooHealthCheck(), FooHealthCheck("bar")]

    def _stop(self):
        if self.stop_error:
            raise self.stop_error


@dataclass
class ServiceStateSubscriber(Observer[ServiceStateEvent]):
    events_received: list[ServiceStateEvent] = field(default_factory=list)
    event: ServiceStateEvent | None = None
    error: Exception | None = None
    completed: bool = False

    def on_next(self, event: ServiceStateEvent) -> None:
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
        commands = Subject()
        commands_observable = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)
        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.state_observable().subscribe(foo_state_observer)
        # signal the service to start
        commands.on_next(ServiceCommand.START)

        # wait until service has started
        while not foo.running:
            sleep(0.001)

        # healthcheck is scheduled to run every second
        # sleep for 2 seconds to give time to run heatlh checks
        sleep(3)

        for healthcheck in foo.healthchecks:
            self.assertIsNotNone(healthcheck.last_result)
            logger.info(f"last healthcheck result: {healthcheck.last_result}")

        # trying to start the service when it's running should be a noop
        commands.on_next(ServiceCommand.START)

        commands.on_next(ServiceCommand.STOP)
        while not foo.stopped:
            sleep(0.001)

        # trying to stop the service when it's stopped should be a noop
        commands.on_next(ServiceCommand.STOP)

        self.assertEqual(
            [
                ServiceStateEvent(foo.name, ServiceState.NEW),
                ServiceStateEvent(foo.name, ServiceState.STARTING),
                ServiceStateEvent(foo.name, ServiceState.RUNNING),
                ServiceStateEvent(foo.name, ServiceState.STOPPING),
                ServiceStateEvent(foo.name, ServiceState.STOPPED),
            ],
            foo_state_observer.events_received,
        )

    def test_service_start_error(self):
        commands = Subject()
        commands_observable = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)
        foo.start_error = Exception("BOOM!")
        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.state_observable().subscribe(foo_state_observer)
        # signal the service to start
        commands.on_next(ServiceCommand.START)

        # wait until service has stopped
        while not foo.stopped:
            sleep(0.001)

        self.assertEqual(
            [
                ServiceStateEvent(foo.name, ServiceState.NEW),
                ServiceStateEvent(foo.name, ServiceState.STARTING),
                ServiceStateEvent(foo.name, ServiceState.START_FAILED),
                ServiceStateEvent(foo.name, ServiceState.STOPPING),
                ServiceStateEvent(foo.name, ServiceState.STOPPED),
            ],
            foo_state_observer.events_received,
        )

        self.assertIsInstance(foo_state_observer.error, ServiceStartError)

    def test_service_stop_error(self):
        commands = Subject()
        commands_observable = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)
        foo.stop_error = Exception("BOOM!")
        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.state_observable().subscribe(foo_state_observer)
        # signal the service to start
        commands.on_next(ServiceCommand.START)

        # wait until service has started
        while not foo.running:
            sleep(0.001)

        commands.on_next(ServiceCommand.STOP)
        while not foo.stopped:
            sleep(0.001)

        # trying to stop the service when it's stopped should be a noop
        commands.on_next(ServiceCommand.STOP)

        self.assertEqual(
            [
                ServiceStateEvent(foo.name, ServiceState.NEW),
                ServiceStateEvent(foo.name, ServiceState.STARTING),
                ServiceStateEvent(foo.name, ServiceState.RUNNING),
                ServiceStateEvent(foo.name, ServiceState.STOPPING),
                ServiceStateEvent(foo.name, ServiceState.STOPPED),
            ],
            foo_state_observer.events_received,
        )

        self.assertIsInstance(foo_state_observer.error, ServiceStopError)

    def test_service_start_stop_error(self):
        commands = Subject()
        commands_observable = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)
        foo.start_error = Exception("START FAILED!")
        foo.stop_error = Exception("STOP FAILED!")
        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.state_observable().subscribe(foo_state_observer)
        # signal the service to start
        commands.on_next(ServiceCommand.START)

        # wait until service has stopped
        while not foo.stopped:
            sleep(0.001)

        commands.on_next(ServiceCommand.STOP)
        while foo.state != ServiceState.STOPPED:
            sleep(0.001)

        # trying to stop the service when it's stopped should be a noop
        commands.on_next(ServiceCommand.STOP)

        self.assertEqual(
            [
                ServiceStateEvent(foo.name, ServiceState.NEW),
                ServiceStateEvent(foo.name, ServiceState.STARTING),
                ServiceStateEvent(foo.name, ServiceState.START_FAILED),
                ServiceStateEvent(foo.name, ServiceState.STOPPING),
                ServiceStateEvent(foo.name, ServiceState.STOPPED),
            ],
            foo_state_observer.events_received,
        )

        self.assertIsInstance(foo_state_observer.error, ServiceStopError)


if __name__ == "__main__":
    unittest.main()
