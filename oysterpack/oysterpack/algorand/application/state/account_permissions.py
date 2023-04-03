"""
Provides support to manage account permissions.
"""

from copy import copy

from beaker import Application
from beaker.decorators import AuthCallable
from pyteal import (
    Expr,
    Seq,
    If,
    App,
    Global,
    Int,
    Subroutine,
    TealType,
    SubroutineFnWrapper,
)
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


def account_permissions_blueprint(app: Application, is_admin: AuthCallable):
    """
    Applies the account permissions blueprint to the app.
    Enables the contract to manage account permissions.

    Notes
    -----
    - application state must contain an AccountPermissions field named: `account_permissions`
    """

    @app.external(authorize=is_admin)
    def grant_permissions(
        account: abi.Account, permissions: abi.Uint64, *, output: abi.Uint64
    ) -> Expr:
        """
        Grants the specified permissions to the specified account.

        :param account: that will be granted permissions
        :param permissions: permission bitmask used to grant permissions
        :returns: account's updated permissions
        """
        account_permissions = app.state.account_permissions[account.address()]
        return Seq(
            account_permissions.grant(permissions),
            output.set(account_permissions.get()),
        )

    @app.external(authorize=is_admin)
    def revoke_permissions(
        account: abi.Account, permissions: abi.Uint64, *, output: abi.Uint64
    ) -> Expr:
        """
        Revoke the specified permissions for the specified account

        :param account: that will be revoked permissions
        :param permissions: permission bitmask used to revoke permissions
        :returns: account's updated permissions
        """
        account_permissions = app.state.account_permissions[account.address()]
        return Seq(
            account_permissions.revoke(permissions),
            output.set(account_permissions.get()),
        )

    @app.external(authorize=is_admin)
    def revoke_all_permissions(account: abi.Account) -> Expr:
        """
        Revokes all permissions from the specified account.

        :param account: all permissions will be revoked from this account
        """
        return app.state.account_permissions[account.address()].revoke_all()

    @app.external(read_only=True)
    def contains_permissions(
        account: abi.Account, permissions: abi.Uint64, *, output: abi.Bool
    ) -> Expr:
        """
        Checks if the account has the specified permissions.
        If the account is not opted in, then False is returned.

        :param account: account to check
        :param permissions: permission bit mask
        :returns: True if the account contains the set of permissions
        """
        return output.set(
            If(
                App.optedIn(account.address(), Global.current_application_id()),
                app.state.account_permissions[account.address()].contains(permissions),
                Int(0),
            )
        )


def account_contains_permissions(app: Application) -> SubroutineFnWrapper:
    """
    :returns: subroutine with the following signature

    @Subroutine(TealType.uint64)
    def _account_contains_permissions(account: abi.Address, permissions: abi.Uint64) -> Expr:
        ...
    """

    @Subroutine(TealType.uint64)
    def _account_contains_permissions(
        account: abi.Address, permissions: abi.Uint64
    ) -> Expr:
        return If(
            App.optedIn(account.get(), Global.current_application_id()),
            app.state.account_permissions[account.get()].contains(permissions),
            Int(0),
        )

    return _account_contains_permissions
