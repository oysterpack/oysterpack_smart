"""
Async Serviec
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import timedelta

from oysterpack.core.service import (
    ServiceLifecycleState,
    ServiceStartError,
    ServiceStopError,
)


class AsyncService(ABC):
    def __init__(self):
        self.__state = ServiceLifecycleState.NEW
        self._logger = logging.getLogger(self.__class__.__name__)

        self.__running = asyncio.Event()
        self.__stopped = asyncio.Event()

    @property
    def state(self) -> ServiceLifecycleState:
        return self.__state

    @property
    def running(self) -> bool:
        """
        :return: True is service is running
        """
        return self.__state == ServiceLifecycleState.RUNNING

    @property
    def stopped(self) -> bool:
        """
        :return: True if service is stopped
        """
        return self.__state == ServiceLifecycleState.STOPPED

    @property
    def name(self) -> str:
        """
        By default, the type class name is used.
        """
        return self.__class__.__name__

    async def await_running(self, timeout: timedelta | None = None):
        """
        Used to await the service is running

        :param timeout: timeout precision is in seconds
        """

        if timeout:
            await asyncio.wait_for(self.__running.wait(), timeout.seconds)
        else:
            await self.__running.wait()

    async def await_stopped(self, timeout: timedelta | None = None):
        """
        Used to await service shutdown

        :param timeout: timeout precision is in seconds
        """
        if timeout:
            await asyncio.wait_for(self.__stopped.wait(), timeout.seconds)
        else:
            await self.__stopped.wait()

    async def start(self):
        if self.__state in (
                ServiceLifecycleState.RUNNING,
                ServiceLifecycleState.STARTING,
        ):
            return

        if self.__state in [ServiceLifecycleState.NEW, ServiceLifecycleState.STOPPED]:
            self.__set_state(ServiceLifecycleState.STARTING)
            try:
                await self._start()
                self.__set_state(ServiceLifecycleState.RUNNING)
            except Exception as err:
                self.__set_state(ServiceLifecycleState.START_FAILED)
                await self.stop()
                raise ServiceStartError(
                    self.name, "error occurred while starting"
                ) from err
        else:
            error = ServiceStartError(
                self.name,
                f"service cannot be started when state is: {self.__state}",
            )
            raise error

    async def stop(self):
        """
        Stop the service

        Notes
        -----
        - The service can only be stopped when state is in [RUNNING, START_FAILED, NEW]
        - When state in [STOPPED, STOPPING], then this is a noop
        """
        if self.__state in (
                ServiceLifecycleState.STOPPED,
                ServiceLifecycleState.STOPPING,
        ):
            return

        if self.__state in (
                ServiceLifecycleState.RUNNING,
                ServiceLifecycleState.START_FAILED,
        ):
            self.__set_state(ServiceLifecycleState.STOPPING)
            try:
                await self._stop()
            except Exception as err:
                self._logger.error("service failed to stop cleanly: %s", err)
            finally:
                self.__set_state(ServiceLifecycleState.STOPPED)
        elif self.__state == ServiceLifecycleState.NEW:
            self.__set_state(ServiceLifecycleState.STOPPED)
        elif self.__state == ServiceLifecycleState.STARTING:
            raise ServiceStopError(
                self.name,
                f"service cannot be stopped when state is: {self.__state}",
            )

    async def restart(self):
        """
        Used to restart the service.
        """

        if self.__state == ServiceLifecycleState.STARTING:
            await self.await_running()

        if self.running:
            await self.stop()

        if self.__state in [ServiceLifecycleState.STOPPED, ServiceLifecycleState.NEW]:
            await self.start()
            return

        await self.await_stopped()
        await self.start()

    def __set_state(self, state: ServiceLifecycleState):
        self._logger.info("state transition: %s -> %s", self.__state.name, state.name)

        self.__state = state

        if state == ServiceLifecycleState.STARTING:
            self.__stopped.clear()
        if state == ServiceLifecycleState.RUNNING:
            self.__running.set()
        if state == ServiceLifecycleState.STOPPING:
            self.__running.clear()
        if state == ServiceLifecycleState.STOPPED:
            self.__stopped.set()

    @abstractmethod
    async def _start(self):
        """
        Service startup hook
        """

    @abstractmethod
    async def _stop(self):
        """
        Service shutdown hook
        """
