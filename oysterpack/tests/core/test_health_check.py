import logging
import unittest
from datetime import timedelta
from threading import Timer
from time import sleep

from oysterpack.core.health_check import (
    HealthCheck,
    HealthCheckImpact,
    HealthCheckStatus,
    YellowHealthCheck,
    RedHealthCheck,
)
from tests.test_support import OysterPackTestCase

logger = logging.getLogger("HealthCheckTestCase")


class FooHealthCheck(HealthCheck):
    error: Exception | None = None

    def __init__(self):
        super().__init__(
            name="foo",
            impact=HealthCheckImpact.HIGH,
            description="Foo health check",
            tags={"database"},
            run_interval=timedelta(seconds=1),
        )

    def execute(self):
        logger.info("executing FooHealthCheck")
        if self.error:
            raise self.error


class MyTestCase(OysterPackTestCase):
    def test_healthcheck(self):
        healthcheck = FooHealthCheck()

        result = healthcheck()
        self.assertEqual(result, healthcheck.last_result)
        self.assertEqual(healthcheck.name, result.name)
        self.assertEqual(HealthCheckStatus.GREEN, result.status)
        self.assertIsNotNone(result.duration)
        self.assertIsNotNone(result.timestamp)
        self.assertIsNone(result.error)

        healthcheck.error = YellowHealthCheck()
        result = healthcheck()
        self.assertEqual(result, healthcheck.last_result)
        self.assertEqual(healthcheck.name, result.name)
        self.assertEqual(HealthCheckStatus.YELLOW, result.status)
        self.assertIsNotNone(result.duration)
        self.assertIsNotNone(result.timestamp)
        self.assertIsInstance(result.error, YellowHealthCheck)

        healthcheck.error = RedHealthCheck()
        result = healthcheck()
        self.assertEqual(result, healthcheck.last_result)
        self.assertEqual(healthcheck.name, result.name)
        self.assertEqual(HealthCheckStatus.RED, result.status)
        self.assertIsNotNone(result.duration)
        self.assertIsNotNone(result.timestamp)
        self.assertIsNotNone(result.error)
        self.assertIsInstance(result.error, RedHealthCheck)

        healthcheck.error = Exception("BOOM!")
        result = healthcheck()
        self.assertEqual(result, healthcheck.last_result)
        self.assertEqual(healthcheck.name, result.name)
        self.assertEqual(HealthCheckStatus.RED, result.status)
        self.assertIsNotNone(result.duration)
        self.assertIsNotNone(result.timestamp)
        self.assertIsNotNone(result.error)

    def test_timer(self):
        healthcheck = FooHealthCheck()

        timer: Timer | None = None  # type: ignore

        def run_healthcheck(healthcheck: HealthCheck):
            healthcheck()
            timer = Timer(
                healthcheck.run_interval.seconds, run_healthcheck, (healthcheck,)
            )
            timer.daemon = True
            timer.start()

        timer = Timer(healthcheck.run_interval.seconds, run_healthcheck, (healthcheck,))
        timer.daemon = True
        timer.start()

        sleep(2)
        if timer:
            timer.cancel()


if __name__ == "__main__":
    unittest.main()
