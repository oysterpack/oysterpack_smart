"""
Provides support for the Command pattern
"""
from abc import ABC, abstractmethod
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
