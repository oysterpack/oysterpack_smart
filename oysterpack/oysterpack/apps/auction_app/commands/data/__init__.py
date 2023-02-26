"""
Provides support for data commands
"""

from abc import ABC

from sqlalchemy.orm import sessionmaker


class SqlAlchemySupport(ABC):
    """
    SqlAlchemySupport
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory
