import pprint
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions

from oysterpack.apps.auction_app.data.auction import (
    Base,
)
from oysterpack.apps.auction_app.healthchecks.database_healthcheck import (
    DatabaseHealthCheck,
)
from oysterpack.core.health_check import HealthCheckStatus
from tests.algorand.test_support import AlgorandTestCase


class DatabaseHealthCheckTestCase(AlgorandTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        self.session_factory = sessionmaker(self.engine)

    def tearDown(self) -> None:
        close_all_sessions()

    def test_healthcheck(self):
        healthcheck = DatabaseHealthCheck(self.session_factory)
        result = healthcheck()
        pprint.pp(result)
        self.assertEqual(HealthCheckStatus.RED, result.status)

        Base.metadata.create_all(self.engine)
        result = healthcheck()
        self.assertEqual(HealthCheckStatus.GREEN, result.status)


if __name__ == "__main__":
    unittest.main()
