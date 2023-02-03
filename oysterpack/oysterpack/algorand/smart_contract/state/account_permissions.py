from copy import copy

from pyteal import Expr
from pyteal.ast import abi

from oysterpack.algorand.smart_contract.state.bitset import AccountBitSet


class AccountPermissions(AccountBitSet):
    """
    Permissions are represented as a bit set.
    Thus, this provides 64 permissions for applications, which should be sufficient for most cases.
    """

    def __init__(self):
        super().__init__(descr="user application permissions")

    def grant(self, permissions: abi.Uint64) -> Expr:
        """
        Grants user the specified permissions.
        """
        return super().set_bits(permissions)

    def revoke(self, permissions: abi.Uint64) -> Expr:
        """
        revokes the specified permissions from the user
        """
        return super().clear_bits(permissions)

    def revoke_all(self) -> Expr:
        """
        revokes all user permissions
        """
        return super().clear()

    def contains(self, permissions: abi.Uint64) -> Expr:
        """
        If the account has the specified permissions, then Int(1) is returned.
        Otherwise, Int(0) is returned.
        """
        return super().contains(permissions)

    def __getitem__(self, acct: Expr) -> "AccountPermissions":
        asv = copy(self)
        asv.acct = acct
        return asv
