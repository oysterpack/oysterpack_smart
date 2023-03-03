"""
ServiceManager
"""
import itertools
import logging
from datetime import timedelta

from reactivex import Observable, Subject
from reactivex.operators import observe_on

from oysterpack.core.rx import default_scheduler
from oysterpack.core.service import (
    Service,
    ServiceCommand,
    ServiceLifecycleEvent,
    ServiceKey,
)


class ServiceManager:
    """
    ServiceManager
    """

    def __init__(self, services: list[Service]):
        """

        Asserts
        -------
        1.At least one service must be specified
        2.Services must be unique. The unique key: (type(service), Service.name)
        """

        if len(services) == 0:
            raise AssertionError("At least 1 service must be specified")

        self._services = {service.key: service for service in services}
        if len(self._services) != len(services):
            dups = [
                key
                for key, _group in itertools.groupby(
                    services, lambda service: service.key
                )
                if len(list(_group)) > 1
            ]
            raise AssertionError(f"Duplicate service keys were found: {dups}")

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

    @property
    def services(self) -> dict[ServiceKey, Service]:
        """
        Returns managed services
        :return: dict[ServiceKey, Service]
        """
        return self._services

    @property
    def service_lifecycle_event_observable(self) -> Observable[ServiceLifecycleEvent]:
        """
        Used to monitor lifecycle events for all managed services.

        :return: Observable[ServiceLifecycleEvent]
        """
        return self._service_lifecycle_event_observable

    def start(self):
        """
        Initiates service startup on all the services being managed.
        """
        for service in self._services.values():
            service._subscribe_commands(  # pylint: disable=protected-access
                self._command_observable
            )

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
        :param timeout: timeout is applied to each service
        """
        for service in self._services.values():
            try:
                service.await_running(timeout)
                self._logger.info("service is running: %s", service.name)
            except TimeoutError as err:
                self._logger.error("service startup timed out: %s", service.name)
                raise err

    def await_stopped(self, timeout: timedelta | None = None):
        """
        Used to await for all services to stop
        :param timeout: timeout is applied to each service
        """
        for service in self._services.values():
            try:
                service.await_stopped(timeout)
                self._logger.info("service is stopped: %s", service.name)
            except TimeoutError as err:
                self._logger.error("service shutdown timed out: %s", service.name)
                raise err
