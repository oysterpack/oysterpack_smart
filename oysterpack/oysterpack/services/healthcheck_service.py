"""
HealthCheck Service
"""
import itertools
from threading import Thread

from reactivex import Observable

from oysterpack.core.health_check import (
    HealthCheck,
    HealthCheckResult,
    HealthCheckStatus,
)
from oysterpack.core.service import Service, ServiceCommand


class HealthCheckService(Service):
    """
    All services support health checks. However, several services can depend on the same healthcheck.
    For example, multiple services may depend on the same database. It would be redundant and inefficient for each
    service to register the same healthcheck.

    The purpose of this service is to enable application wide health checks to be registered.
    """

    def __init__(
        self,
        healthchecks: list[HealthCheck],
        commands: Observable[ServiceCommand] | None = None,
    ):
        super().__init__(commands)
        self._healthchecks = healthchecks[:]

    @property
    def latest_healthcheck_results(self) -> list[HealthCheckResult]:
        """
        :return: list[HealthCheckResult]
        """
        return [
            healthcheck.last_result
            for healthcheck in self._healthchecks
            if healthcheck.last_result
        ]

    @property
    def is_healthy(self) -> bool:
        """
        :return: True if all healthchecks are green
        """
        for healthcheck in self.latest_healthcheck_results:
            if healthcheck.status != HealthCheckStatus.GREEN:
                return False

        return True

    @property
    def latest_healthcheck_results_grouped_by_status(
        self,
    ) -> dict[HealthCheckStatus, list[HealthCheckResult]]:
        """
        :return: latest health check results grouped by status
        """
        grouped_results: dict[HealthCheckStatus, list[HealthCheckResult]] = {}
        for key, group in itertools.groupby(
            self.latest_healthcheck_results, lambda result: result.status
        ):
            if key in grouped_results:
                grouped_results[key] += group
            else:
                grouped_results[key] = list(group)

        return grouped_results

    def run_healthchecks(self):
        """
        Runs all registered health checks. Results are published on the health check Observable stream

        Notes
        -----
        - Healthchecks are run in the background on a separate thread
        """

        def _run_healthchecks():
            for healthcheck in self._healthchecks:
                result = healthcheck()
                self._healthchecks_subject.on_next(result)

        Thread(target=_run_healthchecks, daemon=True).start()

    def _start(self):
        # no additional startup work is required
        # health checks are fully managed by the base Service
        pass

    def _stop(self):
        # no additional shutdown work is required
        # health checks are fully managed by the base Service
        pass
