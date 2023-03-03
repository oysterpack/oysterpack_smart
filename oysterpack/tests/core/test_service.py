import logging
import unittest
from dataclasses import dataclass, field
from datetime import timedelta
from time import sleep

from reactivex import Subject, Observer, Observable
from reactivex.operators import observe_on

from oysterpack.core.health_check import HealthCheck, HealthCheckImpact, HealthCheckResult
from oysterpack.core.rx import default_scheduler
from oysterpack.core.service import (
    Service,
    ServiceCommand,
    ServiceLifecycleEvent,
    ServiceLifecycleState,
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
    start_sleep: timedelta | None = None

    def _start(self):
        if self.start_error:
            raise self.start_error

        self._healthchecks = [FooHealthCheck(), FooHealthCheck("bar")]

        if self.start_sleep:
            logger.info(f"sleeping for {self.start_sleep}")
            sleep(self.start_sleep.seconds)
            logger.info("done sleeping")

    def _stop(self):
        if self.stop_error:
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
    def test_service_lifecycle(self) -> None:
        commands: Subject[ServiceCommand] = Subject()
        commands_observable: Observable[ServiceCommand] = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)

        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.lifecycle_state_observable.subscribe(foo_state_observer)

        healthcheck_results: list[HealthCheckResult] = []

        def on_healthcheck_result(result: HealthCheckResult):
            logger.info(result)
            healthcheck_results.append(result)

        foo.healthchecks_observable.subscribe(on_healthcheck_result)

        # signal the service to start
        commands.on_next(ServiceCommand.START)

        foo.await_running()

        # healthcheck is scheduled to run every second
        # sleep for 2 seconds to give time to run heatlh checks
        sleep(3)

        for healthcheck in foo.healthchecks:
            self.assertIsNotNone(healthcheck.last_result)
            logger.info(f"last healthcheck result: {healthcheck.last_result}")

        # check that healthcheck results were publised on the Observable
        self.assertGreater(len(healthcheck_results), 0)

        # trying to start the service when it's running should be a noop
        commands.on_next(ServiceCommand.START)

        commands.on_next(ServiceCommand.STOP)
        while not foo.stopped:
            sleep(0.001)

        # trying to stop the service when it's stopped should be a noop
        commands.on_next(ServiceCommand.STOP)
        foo.await_stopped()

        self.assertEqual(
            [
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.NEW),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STARTING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.RUNNING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPED),
            ],
            foo_state_observer.events_received,
        )

        with self.subTest("start the stopped service"):
            commands.on_next(ServiceCommand.START)
            foo.await_running()

        with self.subTest("running service can be restarted"):
            foo_state_observer.events_received.clear()
            foo.restart()

            foo.await_running()

            # check events were streamed
            # events are streamed async, thus we need to give them time to stream through
            for _ in range(10):
                try:
                    self.assertEqual(
                        [
                            ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPING),
                            ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPED),
                            ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STARTING),
                            ServiceLifecycleEvent(foo.name, ServiceLifecycleState.RUNNING),
                        ],
                        foo_state_observer.events_received,
                    )
                    break
                except AssertionError:
                    sleep(0.1)


    def test_service_start_error(self):
        commands = Subject()
        commands_observable = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)
        foo.start_error = Exception("BOOM!")
        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.lifecycle_state_observable.subscribe(foo_state_observer)
        # signal the service to start
        commands.on_next(ServiceCommand.START)

        # wait until service has stopped
        while not foo.stopped:
            sleep(0.001)

        self.assertEqual(
            [
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.NEW),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STARTING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.START_FAILED),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPED),
            ],
            foo_state_observer.events_received,
        )

        self.assertIsInstance(foo_state_observer.error, ServiceStartError)

    def test_service_start_timeout(self):
        commands = Subject()
        commands_observable = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)
        foo.start_sleep = timedelta(seconds=2)
        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.lifecycle_state_observable.subscribe(foo_state_observer)
        # signal the service to start
        commands.on_next(ServiceCommand.START)

        with self.assertRaises(TimeoutError):
            foo.await_running(timedelta(seconds=1))

        foo.await_running(timedelta(seconds=2))

        sleep(0.1)  # give the service time to transition to RUNNING

        self.assertEqual(
            [
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.NEW),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STARTING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.RUNNING),
            ],
            foo_state_observer.events_received,
        )

    def test_service_stop_error(self):
        commands = Subject()
        commands_observable = commands.pipe(observe_on(default_scheduler))

        foo = FooService(commands_observable)
        foo.stop_error = Exception("BOOM!")
        # subscribe to service state events
        foo_state_observer = ServiceStateSubscriber()
        foo.lifecycle_state_observable.subscribe(foo_state_observer)
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
        sleep(0.1)  # give time for events to stream through

        self.assertEqual(
            [
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.NEW),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STARTING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.RUNNING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPED),
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
        foo.lifecycle_state_observable.subscribe(foo_state_observer)
        # signal the service to start
        commands.on_next(ServiceCommand.START)

        # wait until service has stopped
        while not foo.stopped:
            sleep(0.001)

        commands.on_next(ServiceCommand.STOP)
        while foo.state != ServiceLifecycleState.STOPPED:
            sleep(0.001)

        # trying to stop the service when it's stopped should be a noop
        commands.on_next(ServiceCommand.STOP)

        self.assertEqual(
            [
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.NEW),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STARTING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.START_FAILED),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPING),
                ServiceLifecycleEvent(foo.name, ServiceLifecycleState.STOPPED),
            ],
            foo_state_observer.events_received,
        )

        self.assertIsInstance(foo_state_observer.error, ServiceStopError)


if __name__ == "__main__":
    unittest.main()
