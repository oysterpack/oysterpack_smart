"""
Activities describe what transactions are doing and are used to validate transactions are properly constructed.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import NewType

from algosdk.transaction import Transaction

from oysterpack.algorand.client.model import AppId

AppActivityId = NewType("AppActivityId", AppId)


@dataclass(slots=True)
class AppActivitySpec(ABC):
    "Defines an application activity specification"

    activity_id: AppActivityId
    name: str
    description: str

    @abstractmethod
    async def validate(self, txns: list[Transaction]):
        """
        :raises InvalidAppActivity: if the set of transactions as a group are not valid per the activity
        """
