import asyncio
import logging
import pprint
import unittest
from concurrent.futures import ProcessPoolExecutor
from logging import LogRecord

from ulid import ULID

from oysterpack.services.asyncio.logging_sevice import AsyncLoggingService

logger = logging.getLogger(__name__)


class FooLogHandler(logging.Handler):
    records: list[LogRecord] = []

    def emit(self, record: LogRecord) -> None:
        self.records.append(record)
        print(self.format(record))


def foo() -> ULID:
    logger = logging.getLogger(__name__)
    id = ULID()
    logger.info("foo: %s", id)
    return id


class LoggingServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.logging_service = AsyncLoggingService(level=logging.DEBUG)
        await self.logging_service.start()
        await self.logging_service.await_running()

    async def asyncTearDown(self) -> None:
        await self.logging_service.stop()
        await self.logging_service.await_stopped()

    async def test_local_logging(self):
        logger.info("Ciao Mundo!")

    async def test_multiprocessing_logging(self):
        with ProcessPoolExecutor() as executor:
            result = await asyncio.get_event_loop().run_in_executor(executor, foo)
            logger.info("result: %s", result)


class LoggingServiceWithHandlersTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.handler = FooLogHandler()
        self.logging_service = AsyncLoggingService(
            level=logging.DEBUG, handlers=[self.handler]
        )
        await self.logging_service.start()
        await self.logging_service.await_running()

    async def asyncTearDown(self) -> None:
        await self.logging_service.stop()
        await self.logging_service.await_stopped()

    async def test_local_logging(self):
        msg = "Ciao Mundo!"
        logger.info(msg)
        await asyncio.sleep(0)
        matches = [record for record in self.handler.records if record.message == msg]
        self.assertEqual(1, len(matches))

    async def test_multiprocessing_logging(self):
        """
        When multiprocessing logging is disabled, then no log records
        from remote multiprocessing tasks should be logged
        """
        with ProcessPoolExecutor() as executor:
            result = await asyncio.get_event_loop().run_in_executor(executor, foo)
            logger.info("result: %s", result)

        await asyncio.sleep(0)
        matches = [
            record
            for record in self.handler.records
            if record.message == f"foo: {result}"
        ]
        self.assertEqual(0, len(matches))


class MultiprocessingEnabledLoggingServiceWithHandlersTestCase(
    unittest.IsolatedAsyncioTestCase
):
    async def asyncSetUp(self) -> None:
        self.handler = FooLogHandler()
        self.logging_service = AsyncLoggingService(
            level=logging.DEBUG,
            handlers=[self.handler],
            multiprocessing_logging_enabled=True,
        )
        await self.logging_service.start()
        await self.logging_service.await_running()

    async def asyncTearDown(self) -> None:
        await self.logging_service.stop()
        await self.logging_service.await_stopped()

    async def test_local_logging(self):
        msg = "Ciao Mundo!"
        logger.info(msg)
        await asyncio.sleep(0)

        msgs = [record.message for record in self.handler.records]
        while msg not in msgs:
            await asyncio.sleep(0)
            msgs = [record.message for record in self.handler.records]

    async def test_multiprocessing_logging(self):
        """
        When multiprocessing logging is enabled, then log records
        from remote multiprocessing tasks should be logged
        """

        with ProcessPoolExecutor() as executor:
            result = await asyncio.get_event_loop().run_in_executor(executor, foo)
            logger.info("result: %s", result)

        await asyncio.sleep(0)

        msgs = [record.message for record in self.handler.records]
        pprint.pp(msgs)
        while f"foo: {result}" not in msgs:
            await asyncio.sleep(0)
            msgs = [record.message for record in self.handler.records]


class MultiprocessingEnabledLoggingServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.logging_service = AsyncLoggingService(
            level=logging.DEBUG,
            multiprocessing_logging_enabled=True,
        )
        await self.logging_service.start()
        await self.logging_service.await_running()

    async def asyncTearDown(self) -> None:
        await self.logging_service.stop()
        await self.logging_service.await_stopped()

    async def test_local_logging(self):
        logger.info("Ciao Mundo!")

    async def test_multiprocessing_logging(self):
        with ProcessPoolExecutor() as executor:
            result = await asyncio.get_event_loop().run_in_executor(executor, foo)
            logger.info("result: %s", result)


if __name__ == "__main__":
    unittest.main()
