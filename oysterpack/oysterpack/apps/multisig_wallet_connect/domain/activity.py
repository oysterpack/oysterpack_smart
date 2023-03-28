"""
Activities describe what transactions are doing and are used to validate transactions are properly constructed.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple

from algosdk.transaction import Transaction

from oysterpack.core.ulid import HashableULID


class TxnActivityId(HashableULID):
    """
    Transaction activity ID

    Transaction activities are used to validate that the transaction is constructed properly per the activity.
    """


class AppActivityId(HashableULID):
    """
    Application activity ID

    Application activity applies to a set of transactions.
    """

@dataclass(slots=True)
class TxnActivitySpec(ABC):
    "Defines a transaction activity specification"

    activity_id: TxnActivityId
    name: str
    description: str

    @abstractmethod
    async def validate(self, txn: Transaction):
        """
        :raises InvalidTxnActivity: if the transaction is not valid per the activity
        """

@dataclass(slots=True)
class AppActivitySpec(ABC):
    "Defines an application activity specification"

    activity_id: AppActivityId
    name: str
    description: str

    @abstractmethod
    async def validate(self, txns: list[Tuple[Transaction, TxnActivityId]]):
        """
        :raises InvalidAppActivity: if the set of transactions as a group are not valid per the activity
        """
