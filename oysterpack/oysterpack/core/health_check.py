"""
Health Checks
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import IntEnum, auto


class HealthCheckStatus(IntEnum):
    """
    HealthCheckStatus
    """

    # healthy
    GREEN = auto()

    # service is functioning but requires attention, e.g.,
    # - resources may be running low (low disk space, high system load, etc)
    # - degraded performance
    # - intermittment failures
    YELLOW = auto()

    # unhealthy, e.g.
    # - service is down
    # - service not meeting SLA
    RED = auto()


class HealthCheckImpact(IntEnum):
    """
    Used to indicate the impact of health check failures in the context of the application or system.

    The impact can be used to prioritize healthcheck failures. For example, the priority order would be
        RED, HIGH
        RED, MEDIUM
        RED, LOW
        YELLOW, HIGH
        YELLOW, MEDIUM
        YELLOW, LOW
    """

    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


class YellowHealthCheck(Exception):
    """
    Indicates HealthCheck is in a YELLOW state
    """


class RedHealthCheck(Exception):
    """
    Indicates HealthCheck is in a RED state
    """


@dataclass(slots=True)
class HealthCheckResult:
    """
    HealthCheckResult
    """

    # HealthCheck.name
    name: str

    status: HealthCheckStatus

    # when the health check was tun
    timestamp: datetime
    # how long it took to run the health check
    duration: timedelta

    error: Exception | None = None


@dataclass(slots=True)
class HealthCheck(ABC):
    """
    HealthCheck
    """

    name: str

    # used to categorize healthchecks, e.g database, algod, algo_indexer
    tags: set[str]
    description: str

    impact: HealthCheckImpact

    # how often to run the healthcheck
    run_interval: timedelta = timedelta(seconds=30)

    last_result: HealthCheckResult | None = field(default=None, init=False)

    def __call__(self) -> HealthCheckResult:
        start = datetime.now(UTC)
        try:
            self.execute()
            self.last_result = HealthCheckResult(
                name=self.name,
                status=HealthCheckStatus.GREEN,
                timestamp=start,
                duration=datetime.now(UTC) - start,
            )
        except YellowHealthCheck as err:
            self.last_result = HealthCheckResult(
                name=self.name,
                status=HealthCheckStatus.YELLOW,
                timestamp=start,
                duration=datetime.now(UTC) - start,
                error=err,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            self.last_result = HealthCheckResult(
                name=self.name,
                status=HealthCheckStatus.RED,
                timestamp=start,
                duration=datetime.now(UTC) - start,
                error=err,
            )
        return self.last_result

    @abstractmethod
    def execute(self):
        """
        Execute the health check

        :exception YellowHealthCheck: indicates healthcheck current status is `YELLLOW`
        :exception RedHealthCheck: indicates healthcheck current status is `RED`
        :exception Exception: any other exception is treated as `RED`
        """
