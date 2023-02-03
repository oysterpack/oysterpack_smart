from copy import copy

from beaker import AccountStateValue
from pyteal import Int, TealType, Expr
from pyteal.ast import abi


class AccountPermissions(AccountStateValue):
    """
    Permissions are represented as a bit set.
    Thus, this provides 64 permissions for applications, which should be sufficient for most cases.
    """

    def __init__(self):
        super().__init__(
            stack_type=TealType.uint64,
            default=Int(0),
            descr="user application permissions",
        )

    def grant(self, permissions: abi.Uint64) -> Expr:
        """
        Grants user the specified permissions.
        """
        return self.set(self.get() | permissions.get())

    def revoke(self, permissions: abi.Uint64) -> Expr:
        """
        revokes the specified permissions from the user
        """
        return self.set(self.get() & ~permissions.get())

    def revoke_all(self) -> Expr:
        """
        revokes all user permissions
        """
        return self.set(Int(0))

    def contains(self, permissions: abi.Uint64) -> Expr:
        """
        If the account has the specified permissions, then Int(1) is returned.
        Otherwise, Int(0) is returned.
        """
        return (self.get() & permissions.get()) == permissions.get()

    def __getitem__(self, acct: Expr) -> "AccountPermissions":
        asv = copy(self)
        asv.acct = acct
        return asv


def decode_permissions_bits(account_permissions: int) -> set[int]:
    """
    Account permissions are encoded as bits, i.e., the account has the permission if the bit is set.

    :param account_permissions:
    :return: permission bits that are set
    """
    assert (
        account_permissions >= 0 and account_permissions <= 1 << 63
    ), "account_permissions must be within the uint64 range"
    if account_permissions == 0:
        return set()
    return {
        i
        for i, bit in enumerate(
            reversed([int(x) for x in f"{account_permissions:064b}"])
        )
        if bit == 1
    }
