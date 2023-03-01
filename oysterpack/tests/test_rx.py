import unittest

import reactivex
from reactivex import Observer


class MyObserver(Observer[int]):
    def on_next(self, value: int):
        print("Got: %s" % value)

    def on_error(self, error: Exception):
        print("Got error: %s" % error)

    def on_completed(self):
        print("Sequence completed")


class RxTestCase(unittest.TestCase):
    def test_rx(self):
        xs = reactivex.from_iterable(range(10))
        xs.subscribe(MyObserver())

    def test_subject(self):
        from reactivex.subject import Subject

        stream = Subject[int]()

        stream.subscribe(lambda x: print("d2: Got: %s" % x))

        stream.on_next(41)

        d = stream.subscribe(lambda x: print("d: Got: %s" % x))

        stream.on_next(42)
        stream.on_next(50)

        d.dispose()
        stream.on_next(43)


if __name__ == "__main__":
    unittest.main()
