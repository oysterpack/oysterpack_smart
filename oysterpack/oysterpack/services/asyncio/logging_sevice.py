"""
Async logging service
"""
import logging
import multiprocessing
from logging.handlers import QueueHandler, QueueListener
from queue import SimpleQueue

from oysterpack.core.async_service import AsyncService
from oysterpack.core.logging import configure_logging


class AsyncLoggingService(AsyncService):
    """
    Reconfigures logging to let handlers do their work on a separate thread from one which does the logging
    """

    def __init__(
        self,
        level: int = logging.WARNING,
        handlers: list[logging.Handler] | None = None,
        multiprocessing_logging_enabled: bool = False,
    ):
        """
        Notes
        -----
        - multiprocessing_logging_enabled
        - If True, then log records from multiprocessing tasks will be collected.
          - The app must ensure that all log records can be pickled.
        - If False, then only local log records will be processed, i.e. log records created within multiprocessing tasks
          will not be logged.

        :param level: root logging level
        :param handlers: root logging handlers
        :param multiprocessing_logging_enabled: If True, then log records from multiprocessing tasks will be collected.
        """
        super().__init__()
        self.level = level
        self.__handlers = handlers[:] if handlers else None
        self.__queue = (
            multiprocessing.Queue()
            if multiprocessing_logging_enabled
            else SimpleQueue()
        )

    async def _start(self) -> None:
        configure_logging(self.level, self.__handlers)

        root = logging.getLogger()
        handlers: list[logging.Handler] = root.handlers[:]
        root.handlers.clear()
        handler = QueueHandler(self.__queue)  # type: ignore
        root.addHandler(handler)

        self.__listener = QueueListener(
            self.__queue,  # type: ignore
            *handlers,
            respect_handler_level=True,
        )
        self.__listener.start()

    async def _stop(self):
        # reset logging
        configure_logging(self.level, self.__handlers)

        if self.__listener:
            self.__listener.stop()
