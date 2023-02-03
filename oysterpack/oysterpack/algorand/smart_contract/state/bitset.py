from copy import copy

from beaker import AccountStateValue, ApplicationStateValue
from pyteal import Int, TealType, Expr
from pyteal.ast import abi


class ApplicationBitSet(ApplicationStateValue):
    """
    BitSet with 64 bits
    """

    def __init__(self, descr: str | None = None):
        super().__init__(
            stack_type=TealType.uint64,
            default=Int(0),
            descr=descr,
        )

    def set_bits(self, mask: abi.Uint64) -> Expr:
        return self.set(self.get() | mask.get())

    def clear_bits(self, mask: abi.Uint64) -> Expr:
        return self.set(self.get() & ~mask.get())

    def clear(self) -> Expr:
        return self.set(Int(0))

    def contains(self, mask: abi.Uint64) -> Expr:
        """
        Returns Int(1) if all bits in the mask are set.
        """
        return (self.get() & mask.get()) == mask.get()


class AccountBitSet(AccountStateValue):
    """
    BitSet with 64 bits
    """

    def __init__(self, descr: str | None = None):
        super().__init__(
            stack_type=TealType.uint64,
            default=Int(0),
            descr=descr,
        )

    def set_bits(self, mask: abi.Uint64) -> Expr:
        return self.set(self.get() | mask.get())

    def clear_bits(self, mask: abi.Uint64) -> Expr:
        return self.set(self.get() & ~mask.get())

    def clear(self) -> Expr:
        return self.set(Int(0))

    def contains(self, mask: abi.Uint64) -> Expr:
        """
        Returns Int(1) if all bits in the mask are set.
        """
        return (self.get() & mask.get()) == mask.get()

    def __getitem__(self, acct: Expr) -> "AccountBitSet":
        asv = copy(self)
        asv.acct = acct
        return asv


def decode_bit_mask(mask: int) -> set[int]:
    """
    :param mask:
    :return: bits that are set
    """
    assert mask >= 0 and mask <= 1 << 63, "mask must be within the uint64 range"
    if mask == 0:
        return set()
    return {
        i
        for i, bit in enumerate(reversed([int(x) for x in f"{mask:064b}"]))
        if bit == 1
    }
