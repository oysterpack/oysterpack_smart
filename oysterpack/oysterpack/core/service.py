import logging
from abc import ABC
from dataclasses import dataclass
from enum import IntEnum, auto
from threading import Timer

from reactivex import Observable, Subject
from reactivex.operators import observe_on
from reactivex.subject import BehaviorSubject

from oysterpack.core.health_check import HealthCheck, HealthCheckResult
from oysterpack.core.rx import default_scheduler


class ServiceState(IntEnum):
    NEW = auto()

    STARTING = auto()

    START_FAILED = auto()

    RUNNING = auto()

    STOPPING = auto()

    STOPPED = auto()


@dataclass(slots=True)
class ServiceStateEvent:
    service_name: str
    state: ServiceState


class ServiceCommand(IntEnum):
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

    def __init__(self, commands: Observable[ServiceCommand]):
        self._state = ServiceState.NEW
        self._logger = logging.getLogger(self.__class__.__name__)

        # setup stream to publish service state events
        self._state_subject: BehaviorSubject[ServiceStateEvent] = BehaviorSubject(
            ServiceStateEvent(self.name, self._state)
        )
        self._state_observable: Observable[
            ServiceStateEvent
        ] = self._state_subject.pipe(observe_on(default_scheduler))

        def on_command(command: ServiceCommand):
            self._logger.info(f"received ServiceCommand: {command.name}")
            match command:
                case ServiceCommand.START:
                    self.start()
                case ServiceCommand.STOP:
                    self.stop()

        commands.subscribe(on_command)

        # healthchecks
        self._healthchecks: list[HealthCheck] = []
        self._healthchecks_subject: Subject[HealthCheckResult] = Subject()
        self._healthchecks_observable: Observable[
            HealthCheckResult
        ] = self._healthchecks_subject.pipe(observe_on(default_scheduler))
        self._healthcheck_timer: Timer | None = None

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def state(self) -> ServiceState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state == ServiceState.RUNNING

    @property
    def stopped(self) -> bool:
        return self._state == ServiceState.STOPPED

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

        if self._state in [ServiceState.RUNNING, ServiceState.STARTING]:
            return

        if self._state == ServiceState.NEW:
            self._state_subject.on_next(self._set_state(ServiceState.STARTING))
            try:
                self._start()
                self._state_subject.on_next(self._set_state(ServiceState.RUNNING))
                for healthcheck in self.healthchecks:
                    schedule_healthcheck(healthcheck)
            except Exception as err:
                self._state_subject.on_next(self._set_state(ServiceState.START_FAILED))
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
        if self._state in [ServiceState.STOPPED, ServiceState.STOPPING]:
            return

        if self._state in [ServiceState.RUNNING, ServiceState.START_FAILED]:
            # stop running health checks
            self._healthchecks_subject.on_completed()
            self._healthchecks_subject.dispose()

            start_failed = self._state == ServiceState.START_FAILED
            self._state_subject.on_next(self._set_state(ServiceState.STOPPING))
            try:
                self._stop()
                self._state_subject.on_next(self._set_state(ServiceState.STOPPED))
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
                self._state_subject.on_next(self._set_state(ServiceState.STOPPED))
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
        elif self._state == ServiceState.NEW:
            self._state_subject.on_next(self._set_state(ServiceState.STOPPED))
            self._state_subject.on_completed()
            self._state_subject.dispose()
        elif self._state == ServiceState.STARTING:
            error = ServiceStopError(
                self.name,
                f"service cannot be stopped when state is: {self._state}",
            )
            self._state_subject.on_error(error)
            raise error

    def state_observable(self) -> Observable[ServiceStateEvent]:
        return self._state_observable

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

    def _set_state(self, state: ServiceState) -> ServiceStateEvent:
        self._logger.info(f"state transition: {self._state.name} -> {state.name}")
        self._state = state
        return ServiceStateEvent(self.name, state)
