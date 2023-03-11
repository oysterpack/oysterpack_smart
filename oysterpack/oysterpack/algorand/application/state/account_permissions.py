"""
Provides support to manage account permissions.
"""

from copy import copy

from pyteal import Expr
from pyteal.ast import abi

from oysterpack.algorand.application.state.bitset import AccountBitSet


class AccountPermissions(AccountBitSet):  # pylint: disable=too-many-ancestors
    """
    Permissions are represented as a bit set.
    Thus, this provides 64 permissions for applications, which should be sufficient for most cases.

    Permissions are stored as account local state.
    """

    def __init__(self):
        super().__init__(descr="user application permissions")

    def grant(self, permissions: abi.Uint64) -> Expr:
        """
        Grants user the specified permissions.
        """
        return self.set_bits(permissions)

    def revoke(self, permissions: abi.Uint64) -> Expr:
        """
        revokes the specified permissions from the user
        """
        return self.clear_bits(permissions)

    def revoke_all(self) -> Expr:
        """
        revokes all user permissions
        """
        return self.clear()

    def __getitem__(self, acct: Expr) -> "AccountPermissions":
        asv = copy(self)
        asv._acct = acct
        return asv
