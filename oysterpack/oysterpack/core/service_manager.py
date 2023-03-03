"""
ServiceManager
"""
import logging
from datetime import timedelta

from reactivex import Observable, Subject
from reactivex.operators import observe_on

from oysterpack.core.rx import default_scheduler
from oysterpack.core.service import Service, ServiceCommand, ServiceLifecycleEvent


class ServiceManager:
    """
    ServiceManager
    """

    def __init__(self, services: list[Service]):
        if len(services) == 0:
            raise AssertionError("There must be at least 1 service")

        self.services = services[:]
        self._logger = logging.getLogger(self.__class__.__name__)

        # initialize Observable[ServiceLifeCycleState]
        self._service_lifecycle_subject: Subject[ServiceLifecycleEvent] = Subject()
        for service in services:
            service.lifecycle_state_observable.subscribe(
                self._service_lifecycle_subject
            )
        self._service_lifecycle_event_observable: Observable[
            ServiceLifecycleEvent
        ] = self._service_lifecycle_subject.pipe(observe_on(default_scheduler))

        # initialize Observable[ServiceCommand]
        self._command_subject: Subject[ServiceCommand] = Subject()  # type: ignore
        self._command_observable: Observable[  # type: ignore
            ServiceCommand
        ] = self._command_subject.pipe(observe_on(default_scheduler))

    def start(self):
        """
        Initiates service startup on all the services being managed.
        """
        for service in self.services:
            service._subscribe_commands(self._command_observable)

        self._command_subject.on_next(ServiceCommand.START)

    def stop(self):
        """
        Initiates service shutdown on all the services being managed
        :return:
        """
        self._command_subject.on_next(ServiceCommand.STOP)

    def await_running(self, timeout: timedelta | None = None):
        """
        Used to await for all services to start
        :param timeout: timeout is applied to each srevice
        """
        for service in self.services:
            try:
                service.await_running(timeout)
                self._logger.info(f"service is running: {service.name}")
            except TimeoutError as err:
                self._logger.error(f"service startup timed out: {service.name}")
                raise err

    def await_stopped(self, timeout: timedelta | None = None):
        for service in self.services:
            try:
                service.await_stopped(timeout)
                self._logger.info(f"service is stopped: {service.name}")
            except TimeoutError as err:
                self._logger.error(f"service shutdown timed out: {service.name}")
                raise err

    @property
    def service_lifecycle_event_observable(self) -> Observable[ServiceLifecycleEvent]:
        return self._service_lifecycle_event_observable
