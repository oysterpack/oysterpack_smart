import logging
import unittest
from logging import Logger

from oysterpack.services.asyncio.logging_sevice import AsyncLoggingService

logging_service = AsyncLoggingService(
    level=logging.DEBUG, multiprocessing_logging_enabled=False
)


class OysterPackTestCase(unittest.TestCase):
    maxDiff = None

    def get_logger(self, name: str) -> Logger:
        return logging.getLogger(f"{self.__class__.__name__}.{name}")


class OysterPackIsolatedAsyncioTestCase(unittest.IsolatedAsyncioTestCase):
    maxDiff = None

    async def asyncSetUp(self) -> None:
        if logging_service.running:
            return
        await logging_service.start()
        await logging_service.await_running()

    def get_logger(self, name: str) -> Logger:
        return logging.getLogger(f"{self.__class__.__name__}.{name}")


if __name__ == "__main__":
    unittest.main()
