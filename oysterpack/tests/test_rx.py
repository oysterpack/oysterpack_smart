import unittest
from threading import current_thread
from time import sleep

import reactivex
from reactivex import Observer
from reactivex import operators as ops
from reactivex.abc import ObserverBase, DisposableBase, SchedulerBase
from reactivex.internal import SequenceContainsNoElementsError

from oysterpack.core.rx import default_scheduler


class MyObserver(Observer[int]):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def on_next(self, value: int):
        print(f"{current_thread().name} :: {self.name} :: on_next({value})")

    def on_error(self, error: Exception):
        print(f"{current_thread().name} :: {self.name} :: on_error({error})")

    def on_completed(self):
        print(f"{current_thread().name} :: {self.name} :: on_completed)")
        self.dispose()


class RxTestCase(unittest.TestCase):
    def test_rx(self):
        xs = reactivex.from_iterable(range(10))
        xs.subscribe(MyObserver("A"))

    def test_subscribe_on(self):
        from reactivex.subject import Subject

        stream = Subject[int]()

        def subscription(
            observer: ObserverBase[int], scheduler: SchedulerBase | None = None
        ) -> DisposableBase:
            return stream.subscribe(observer, scheduler=scheduler)

        observable = reactivex.create(subscription).pipe(
            ops.observe_on(default_scheduler),
        )

        observable.subscribe(MyObserver("A"))
        observable.subscribe(MyObserver("B"))
        sleep(0.1)
        for i in range(1, 20):
            stream.on_next(i)

        stream.on_completed()

        try:
            observable.run()
        except SequenceContainsNoElementsError as err:
            print(err)

    def test_subject(self):
        from reactivex.subject import Subject

        stream = Subject[int]()

        observable = stream.pipe(
            ops.subscribe_on(default_scheduler),
            ops.observe_on(default_scheduler),
        )

        observable.subscribe(MyObserver("A"))
        observable.subscribe(MyObserver("B"))
        sleep(0.1)
        for i in range(1, 20):
            stream.on_next(i)

        stream.on_completed()

        try:
            observable.run()
        except SequenceContainsNoElementsError as err:
            print(err)


if __name__ == "__main__":
    unittest.main()
