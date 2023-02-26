"""
Provides support for the Command pattern
"""
import logging
from abc import ABC, abstractmethod
from logging import Logger
from typing import TypeVar, Generic

Args = TypeVar("Args")

Result = TypeVar("Result")


class Command(Generic[Args, Result], ABC):
    """
    Commands are invoked as functions
    """

    @abstractmethod
    def __call__(self, args: Args) -> Result:
        """
        Executes the command
        """

    def get_logger(self, name: str | None = None) -> Logger:
        """
        Returns a logger using the class name as the logger name.
        If `name` is specifed, then it is appended to the class name: `{self.__class__.__name__}.{name}`
        """
        if name is None:
            return logging.getLogger(self.__class__.__name__)

        return logging.getLogger(f"{self.__class__.__name__}.{name}")
