import logging
import time


# TODO: add support to log App ID, app version, PID, thread ID
def configure_logging(level: int = logging.WARNING):
    """
    Confifues logging format and log level.

    :param level: default = logging.WARNING
    :return: None

    - log format: %(asctime)s %(levelname)s|%(name)s: %(message)s
    - timestamps are UTC
    - best practice is to retrieve a logger using the module's name:

    >>> configure_logging(level=logging.DEBUG)
    >>> logger = logging.getLogger('oysterpack.algorand')
    >>> logger.info('Algorand is the future of finance') # doctest: +SKIP
    2023-01-09 14:48:20,594 INFO|oysterpack.algorand: Algorand is the future of finance

    """
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(format=f'%(asctime)s [%(levelname)s] [%(name)s] %(message)s', level=level)
    logging.captureWarnings(True)


def full_class_name(__obj) -> str:
    "Returns the fully qualified class name for the specified object"

    _class = __obj.__class__
    if _class.__module__ == 'builtins':
        return _class.__qualname__  # avoid outputs like 'builtins.str'
    return f'{_class.__module__}.{_class.__qualname__}'
