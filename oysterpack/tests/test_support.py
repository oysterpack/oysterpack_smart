import logging
import unittest
from logging import Logger

from oysterpack.core.logging import configure_logging

configure_logging(level=logging.DEBUG)


class OysterPackTestCase(unittest.TestCase):
    maxDiff = None
    
    def get_logger(self, name: str) -> Logger:
        return logging.getLogger(f"{self.__class__.__name__}.{name}")


if __name__ == "__main__":
    unittest.main()
