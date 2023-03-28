import asyncio
import pickle
import unittest
from asyncio import FIRST_EXCEPTION
from datetime import timedelta
from pathlib import PurePath

from ulid import ULID

from tests.algorand.test_support import AlgorandTestCase
from tests.test_support import OysterPackIsolatedAsyncioTestCase


class MyTestCase(AlgorandTestCase, OysterPackIsolatedAsyncioTestCase):
    async def test_asyncio_wait(self):
        async def foo(
            msg: str, err: Exception | None = None, sleep: timedelta | None = None
        ):
            if err is not None:
                raise err

            if sleep is not None:
                print(f"sleeping for: {sleep.total_seconds()}")
                await asyncio.sleep(sleep.total_seconds())

            return msg

        task1 = asyncio.create_task(foo("1"))
        task2 = asyncio.create_task(foo("2"))
        task3 = asyncio.create_task(foo("3", err=Exception("BOOM!")))
        task4 = asyncio.create_task(foo("4", sleep=timedelta(hours=1)))

        (done, pending) = await asyncio.wait(
            [
                task1,
                task2,
                task3,
                task4,
            ],
            return_when=FIRST_EXCEPTION,
        )
        print(f"len(done) = {len(done)}")
        print(f"len(pending) = {len(pending)}")
        self.assertGreaterEqual(len(pending), 1)
        for task in done:
            print(
                f"done={task.done()}, cancelled={task.cancelled()}, exception={task.exception()}"
            )
        self.assertEqual(
            1, len([task for task in done if task.exception() is not None])
        )

        for task in pending:
            task.cancel()

    def test_quick(self):
        path = PurePath("oysterpack", "wallet", str(ULID()))
        print(path.as_posix())

        path_bytes = pickle.dumps(path)
        path2 = pickle.loads(path_bytes)
        self.assertEqual(path, path2)

    def test_exception_group(self):
        err = ExceptionGroup(
            "BOOM",
            (Exception("ERR1"),
            Exception("ERR2"))
        )

        print(err.exceptions[0])


if __name__ == "__main__":
    unittest.main()
