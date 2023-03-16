import unittest

from oysterpack.core.async_service import AsyncService
from oysterpack.core.service import ServiceLifecycleState
from test_support import OysterPackIsolatedAsyncioTestCase


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
        foo = Foo()
        self.assertEqual(ServiceLifecycleState.NEW, foo.state)

        await foo.start()
        await foo.await_running()
        self.assertEqual(ServiceLifecycleState.RUNNING, foo.state)

        await foo.stop()
        await foo.await_stopped()
        self.assertEqual(ServiceLifecycleState.STOPPED, foo.state)


if __name__ == '__main__':
    unittest.main()
