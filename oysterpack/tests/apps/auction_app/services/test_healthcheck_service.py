import unittest
from datetime import timedelta
from pathlib import Path
from time import sleep

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.healthchecks.database_healthcheck import (
    DatabaseHealthCheck,
)
from oysterpack.apps.auction_app.services.healthcheck_service import HealthCheckService
from oysterpack.core.health_check import (
    HealthCheckResult,
    HealthCheckImpact,
    HealthCheck,
    HealthCheckStatus,
)
from oysterpack.core.logging import get_logger
from tests.test_support import OysterPackTestCase


class FooHealthCheck(HealthCheck):
    error: Exception | None = None

    def __init__(self, name: str = "foo"):
        super().__init__(
            name=name,
            impact=HealthCheckImpact.HIGH,
            description="Foo health check",
            tags={"database"},
            run_interval=timedelta(seconds=1),
        )

    def execute(self):
        if self.error:
            raise self.error


class HealthCheckServiceTestCase(OysterPackTestCase):
    def setUp(self) -> None:
        # in-memory database canot be used here because the import process runs in a separate thread
        db_file = Path(f"{self.__class__.__name__}.sqlite")
        if db_file.exists():
            Path.unlink(db_file)
        self.engine = create_engine(f"sqlite:///{db_file}", echo=False)
        Base.metadata.create_all(self.engine)

        self.session_factory = sessionmaker(self.engine)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_healthcheck_service(self) -> None:
        logger = get_logger(self)

        foo = FooHealthCheck()
        bar = FooHealthCheck("bar")
        healthcheck_service = HealthCheckService(
            healthchecks=[
                DatabaseHealthCheck(self.session_factory),
                foo,
                bar,
            ]
        )

        self.assertEqual(0, len(healthcheck_service.latest_healthcheck_results))

        healthcheck_service.start()

        def healthcheck_subscriber(healthcheck_result: HealthCheckResult):
            logger.info(healthcheck_result)

        healthcheck_service.healthchecks_observable.subscribe(healthcheck_subscriber)

        healthcheck_service.run_healthchecks()

        while len(healthcheck_service.latest_healthcheck_results) != 3:
            sleep(0.1)

        self.assertTrue(healthcheck_service.is_healthy)

        # trigger a healthcheck to fail
        foo.error = Exception("BOOM!")
        healthcheck_service.run_healthchecks()

        while healthcheck_service.is_healthy:
            sleep(0.1)

        results_grouped_by_status = (
            healthcheck_service.latest_healthcheck_results_grouped_by_status
        )
        self.assertEqual(2, len(results_grouped_by_status[HealthCheckStatus.GREEN]))
        self.assertEqual(1, len(results_grouped_by_status[HealthCheckStatus.RED]))


if __name__ == "__main__":
    unittest.main()
