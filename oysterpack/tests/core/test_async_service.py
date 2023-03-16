import unittest

from oysterpack.core.async_service import AsyncService
from oysterpack.core.service import ServiceLifecycleState, ServiceStartError, ServiceStopError, ServiceExceptionGroup
from tests.test_support import OysterPackIsolatedAsyncioTestCase


class Foo(AsyncService):

    def __init__(
            self,
            start_err: Exception | None = None,
            stop_err: Exception | None = None,
    ):
        super().__init__()
        self.start_err = start_err
        self.stop_err = stop_err

    async def _start(self):
        if self.start_err:
            raise self.start_err

    async def _stop(self):
        if self.stop_err:
            raise self.stop_err


class AsyncServiceTestCase(OysterPackIsolatedAsyncioTestCase):

    async def test_service_lifecycle(self):
        logger = self.get_logger("test_service_lifecycle")

        foo = Foo()
        self.assertEqual(ServiceLifecycleState.NEW, foo.state)

        await foo.start()
        await foo.await_running()
        self.assertEqual(ServiceLifecycleState.RUNNING, foo.state)

        await foo.stop()
        await foo.await_stopped()
        self.assertEqual(ServiceLifecycleState.STOPPED, foo.state)

        with self.subTest("stopped service can be restarted"):
            await foo.start()
            await foo.await_running()
            self.assertEqual(ServiceLifecycleState.RUNNING, foo.state)

        with self.subTest("running service can be restarted"):
            await foo.restart()
            await foo.await_running()
            self.assertEqual(ServiceLifecycleState.RUNNING, foo.state)

        with self.subTest("when service fails to start, ServiceStartError is raised"):
            foo = Foo(start_err=Exception("BOOM!"))
            with self.assertRaises(ServiceStartError) as err:
                await foo.start()
            logger.error(err.exception)
            self.assertTrue(foo.stopped)

        with self.subTest("when service fails to stop, ServiceStopError is raised"):
            foo = Foo(stop_err=Exception("BOOM!"))
            await foo.start()
            await foo.await_running()

            with self.assertRaises(ServiceStopError) as err:
                await foo.stop()
            logger.error(err.exception)
            self.assertTrue(foo.stopped)

        with self.subTest("when service fails to start, and then an error is raised while stopping"):
            foo = Foo(
                start_err=Exception("BOOM!"),
                stop_err=Exception("BOOM!!"),
            )
            with self.assertRaises(ServiceExceptionGroup) as err:
                await foo.start()
            logger.error(err.exception)
            self.assertTrue(foo.stopped)


if __name__ == '__main__':
    unittest.main()
