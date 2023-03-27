import asyncio
import pickle
import unittest
from asyncio import FIRST_EXCEPTION
from datetime import timedelta

from ulid import ULID

from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    ErrCode,
    SignTransactionsError,
)
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
        err = SignTransactionsError(
            code=ErrCode.InvalidTxnActivityId,
            message=f"invalid transaction activity ID: {ULID()}",
        )

        err_bytes = pickle.dumps(err.to_failure())
        failure = pickle.loads(err_bytes)
        self.assertEqual(err.to_failure(), failure)


if __name__ == "__main__":
    unittest.main()
