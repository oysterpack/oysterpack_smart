from enum import IntEnum, auto
from typing import Final

from beaker import Application, ApplicationStateValue
from beaker.decorators import create
from pyteal import TealType, Expr, Seq, Int
from pyteal.ast import abi


class AuctionStatus(IntEnum):
    New = auto()
    Initialized = auto()
    Cancelled = auto()
    Started = auto()
    BidAccepted = auto()
    Finalized = auto()


class Auction(Application):
    seller: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        static=True,
    )

    status: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(AuctionStatus.New.value),
    )

    @create
    def create(self, seller: abi.Account) -> Expr:
        return Seq(
            self.initialize_application_state(), self.seller.set(seller.address())
        )
