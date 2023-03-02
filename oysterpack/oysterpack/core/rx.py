"""
Provides reactivex support
"""
import multiprocessing

from reactivex.scheduler import ThreadPoolScheduler
from reactivex.scheduler.scheduler import Scheduler

default_scheduler: Scheduler = ThreadPoolScheduler(multiprocessing.cpu_count())


def threadpool_scheduler(max_workers: int | None = None) -> ThreadPoolScheduler:
    """
    :param max_workers: if not specified, the max workers will be set to the CPU count
    """
    return ThreadPoolScheduler(
        max_workers if max_workers else multiprocessing.cpu_count()
    )
