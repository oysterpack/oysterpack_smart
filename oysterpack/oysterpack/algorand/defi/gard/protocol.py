from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, NewType

from oysterpack.algorand.client.model import MicroAlgos

MicroGard = NewType("MicroGard", int)
MicroGAlgos = NewType("MicroGAlgos", int)


class CollateralAsset(Enum):
    ALGO = auto()
    GALGO = auto()


@dataclass
class CollateralDebtPosition:
    id: int
    asset: CollateralAsset
    balance: int
    borrowed_gard_balance: int


class GardProtocol(Protocol):
    def create_algo_cdp(self, algo_amount: MicroAlgos, gard_borrow_amount: MicroGard):
        ...
