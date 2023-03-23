"""
Provides support for logging
"""

import logging
import time
from typing import Any


def configure_logging(
    level: int = logging.WARNING,
    handlers: list[logging.Handler] | None = None,
):
    """
    Configures logging format and log level.

    :param level: default = logging.WARNING
    :return: None

    - log format: %(asctime)s [%(levelname)s] [%(name)s] %(message)s
    - timestamps are UTC
    - best practice is to retrieve a logger using the module's name:

    >>> configure_logging(level=logging.DEBUG)
    >>> logger = logging.getLogger('oysterpack.algorand')
    >>> logger.info('Algorand is the future of finance') # doctest: +SKIP
    2023-01-09 14:48:20,594 [INFO] [oysterpack.algorand] Algorand is the future of finance

    """
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        level=level,
        handlers=handlers,
        force=True,
    )
    logging.captureWarnings(True)


def get_logger(obj: Any, name: str | None = None) -> logging.Logger:
    """
    Returns a logger using the class name as the logger name.
    If `name` is specifed, then it is appended to the class name: `{self.__class__.__name__}.{name}`
    """
    logger = logging.getLogger(obj.__class__.__name__)
    if name is None:
        return logger

    return logger.getChild(name)
