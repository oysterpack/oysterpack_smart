import logging
from abc import ABC
from dataclasses import dataclass
from datetime import timedelta
from enum import IntEnum, auto
from threading import Timer, Event

from reactivex import Observable, Subject
from reactivex.operators import observe_on
from reactivex.subject import BehaviorSubject

from oysterpack.core.health_check import HealthCheck, HealthCheckResult
from oysterpack.core.rx import default_scheduler


class ServiceLifecycleState(IntEnum):
    """
    Service lifecycle states

    Normal service lifecycle: NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
    """

    NEW = auto()

    STARTING = auto()

    START_FAILED = auto()

    RUNNING = auto()

    STOPPING = auto()

    STOPPED = auto()


@dataclass(slots=True)
class ServiceLifecycleEvent:
    """
    Service lifecycle state events
    """

    service_name: str
    state: ServiceLifecycleState


class ServiceCommand(IntEnum):
    """
    Commands used to manage the service.
    """

    START = auto()
    STOP = auto()


@dataclass(slots=True)
class ServiceError(Exception):
    """
    Service failed to start
    """

    service_name: str
    cause: Exception | str

    def __str__(self) -> str:
        return f"{self.service_name} : {self.cause}"


class ServiceStartError(ServiceError):
    """
    Service failed to start
    """


class ServiceStopError(ServiceError):
    """
    Error occurred while trying to stop the service.
    """


class Service(ABC):
    """
    All application services should extend Service. If the service has any startup/shutdown work to do, then it should
    override the `Service._start` and `Service._stop` methods.

    Features
    --------
    - Services have a defined lifecycle. The service lifecycle states are defined by `ServiceState`.
    - Services can be signalled to start and stop async. Services subscribe to an `Observable[ServiceCommand]`
    - Service lifecycle events are published on an Observable[ServiceStateEvent]
    - Services define and schedule their own health checks. Healthcheck results are published on an
      Observable[HealthCheckResult].
    """

    def __init__(self, commands: Observable[ServiceCommand] | None = None):
        self._state = ServiceLifecycleState.NEW
        self._logger = logging.getLogger(self.__class__.__name__)

        # setup stream to publish service state events
        self._state_subject: BehaviorSubject[ServiceLifecycleEvent] = BehaviorSubject(
            ServiceLifecycleEvent(self.name, self._state)
        )
        self._state_observable: Observable[
            ServiceLifecycleEvent
        ] = self._state_subject.pipe(observe_on(default_scheduler))

        self._subscribe_commands(commands)

        # healthchecks
        self._healthchecks: list[HealthCheck] = []
        self._healthchecks_subject: Subject[HealthCheckResult] = Subject()
        self._healthchecks_observable: Observable[
            HealthCheckResult
        ] = self._healthchecks_subject.pipe(observe_on(default_scheduler))
        self._healthcheck_timer: Timer | None = None

        self._running_event = Event()
        self._stopped_event = Event()

    def _subscribe_commands(self, commands: Observable[ServiceCommand] | None = None):
        if commands:

            def on_command(command: ServiceCommand):
                self._logger.info(f"received ServiceCommand: {command.name}")
                match command:
                    case ServiceCommand.START:
                        self.start()
                    case ServiceCommand.STOP:
                        self.stop()

            commands.subscribe(on_command)

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def state(self) -> ServiceLifecycleState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state == ServiceLifecycleState.RUNNING

    def await_running(self, timeout: timedelta | None = None):
        """
        Used to await the service is running
        """
        if not self._running_event.wait(timeout.seconds if timeout else None):
            raise TimeoutError

    def await_stopped(self, timeout: timedelta | None = None):
        """
        Used to await service shutdown
        """
        if not self._stopped_event.wait(timeout.seconds if timeout else None):
            raise TimeoutError

    @property
    def stopped(self) -> bool:
        return self._state == ServiceLifecycleState.STOPPED

    @property
    def healthchecks(self) -> list[HealthCheck]:
        return self._healthchecks[:]

    def start(self):
        """
        Start the service

        Notes
        -----
        - The service can only be started when service state == NEW
        - When state is in [RUNNING, STARTING], then this is a noop
        - If en error occurs while trying to start the service, then stop will be triggered to give the service
          a chance to clean up any resources while trying to start.
          - the error will be published on the Observable stream and the error will be raised
        """

        def schedule_healthcheck(healthcheck: HealthCheck):
            def run_healthcheck(healthcheck: HealthCheck):
                healthcheck()
                self._healthcheck_timer = Timer(
                    healthcheck.run_interval.seconds, run_healthcheck, (healthcheck,)
                )
                self._healthcheck_timer.daemon = True
                self._healthcheck_timer.start()

            self._healthcheck_timer = Timer(
                healthcheck.run_interval.seconds, run_healthcheck, (healthcheck,)
            )
            self._healthcheck_timer.daemon = True
            self._healthcheck_timer.start()
            self._logger.info(f"scheduled healthcheck: {healthcheck}")

        if self._state in [
            ServiceLifecycleState.RUNNING,
            ServiceLifecycleState.STARTING,
        ]:
            return

        if self._state == ServiceLifecycleState.NEW:
            self._state_subject.on_next(self._set_state(ServiceLifecycleState.STARTING))
            try:
                self._start()
                self._state_subject.on_next(
                    self._set_state(ServiceLifecycleState.RUNNING)
                )
                for healthcheck in self.healthchecks:
                    schedule_healthcheck(healthcheck)
            except Exception as err:
                self._state_subject.on_next(
                    self._set_state(ServiceLifecycleState.START_FAILED)
                )
                self.stop()
                raise ServiceStartError(
                    self.name, "error occurred while starting"
                ) from err
        else:
            error = ServiceStartError(
                self.name,
                f"service cannot be started when state is: {self._state}",
            )
            self._state_subject.on_error(error)
            raise error

    def stop(self):
        """
        Stop the service

        Notes
        -----
        - The service can only be stopped when state is in [RUNNING, START_FAILED, NEW]
        - When state in [STOPPED, STOPPING], then this is a noop
        """
        if self._state in [
            ServiceLifecycleState.STOPPED,
            ServiceLifecycleState.STOPPING,
        ]:
            return

        if self._state in [
            ServiceLifecycleState.RUNNING,
            ServiceLifecycleState.START_FAILED,
        ]:
            # stop running health checks
            self._healthchecks_subject.on_completed()
            self._healthchecks_subject.dispose()

            start_failed = self._state == ServiceLifecycleState.START_FAILED
            self._state_subject.on_next(self._set_state(ServiceLifecycleState.STOPPING))
            try:
                self._stop()
                self._state_subject.on_next(
                    self._set_state(ServiceLifecycleState.STOPPED)
                )
                if start_failed:
                    self._state_subject.on_error(
                        ServiceStartError(
                            self.name,
                            "service was stopped because it failed to start",
                        )
                    )
                else:
                    self._state_subject.on_completed()
            except Exception as err:
                self._state_subject.on_next(
                    self._set_state(ServiceLifecycleState.STOPPED)
                )
                if start_failed:
                    self._state_subject.on_error(
                        ServiceStopError(
                            self.name,
                            "service failed to start, and an error occurred trying to stop it",
                        )
                    )
                else:
                    self._state_subject.on_error(ServiceStopError(self.name, err))
                raise ServiceStopError(
                    self.name, "error occurred while stopping"
                ) from err
            finally:
                self._state_subject.dispose()
                if self._healthcheck_timer:
                    self._healthcheck_timer.cancel()
        elif self._state == ServiceLifecycleState.NEW:
            self._state_subject.on_next(self._set_state(ServiceLifecycleState.STOPPED))
            self._state_subject.on_completed()
            self._state_subject.dispose()
        elif self._state == ServiceLifecycleState.STARTING:
            error = ServiceStopError(
                self.name,
                f"service cannot be stopped when state is: {self._state}",
            )
            self._state_subject.on_error(error)
            raise error

    @property
    def lifecycle_state_observable(self) -> Observable[ServiceLifecycleEvent]:
        return self._state_observable

    @property
    def healthchecks_observable(self) -> Observable[HealthCheckResult]:
        return self._healthchecks_observable

    def _start(self):
        """
        Override to perform any startup work.

        Notes
        -----
        - Service HealthCheck(s) are expected to be created during startup
        """
        pass

    def _stop(self):
        """
        override to perform any shutdown work
        """
        pass

    def _set_state(self, state: ServiceLifecycleState) -> ServiceLifecycleEvent:
        self._logger.info(f"state transition: {self._state.name} -> {state.name}")

        self._state = state

        if state == ServiceLifecycleState.RUNNING:
            self._running_event.set()
        if state == ServiceLifecycleState.STOPPED:
            self._stopped_event.set()

        return ServiceLifecycleEvent(self.name, state)
