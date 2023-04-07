"""
App contract
"""
from enum import IntEnum
from typing import Final

from beaker import Application, GlobalStateValue
from beaker.lib.storage import BoxMapping
from pyteal import Expr, TealType, Seq, Txn, If, Subroutine, Int
from pyteal.ast import abi

from oysterpack.algorand.application.state import account_permissions
from oysterpack.algorand.application.state.account_permissions import (
    AccountPermissions,
    account_permissions_blueprint,
)


class WalletConnectAppState:
    """
    WalletConnectApp state
    """

    name: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        static=True,
        descr="application name",
    )
    url: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        static=True,
        descr="application URL",
    )
    enabled: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="when disabled, app messages sent to the WalletConnectServices will be rejected: disabled=0, enabled=1",
    )

    # global admin still needs to opt in to the contract
    # when the global admin account opts in, the account is granted admin permissions
    admin: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        descr="global admin account",
    )
    account_permissions: Final[AccountPermissions] = AccountPermissions()

    # keys used by the app to send messages to the WalletConnectService
    # SigningAddress -> EncryptionAddress
    keys: Final[BoxMapping] = BoxMapping(abi.Address, abi.Address)


class Permission(IntEnum):
    """
    Permission
    """

    # Admin manages permissions for other accounts
    Admin = 1 << 0

    # Permissions for managing keys
    RegisterKeys = 1 << 1
    DeleteKeys = 1 << 2

    # Permissions for enabling/disabling the app
    EnableApp = 1 << 3
    DisableApp = 1 << 4


app = Application("WalletConnectApp", state=WalletConnectAppState())
account_contains_permissions = account_permissions.account_contains_permissions(app)


def contains_permission(account: Expr, permission: Permission):
    return Seq(
        (address := abi.Address()).set(account),
        (perm := abi.Uint64()).set(Int(permission.value)),
        account_contains_permissions(address, perm),
    )


@Subroutine(TealType.uint64)
def is_admin(account: Expr):
    return contains_permission(account, Permission.Admin)


@Subroutine(TealType.uint64)
def contains_register_key_perm(account: Expr):
    return contains_permission(account, Permission.RegisterKeys)


app.apply(account_permissions_blueprint, is_admin=is_admin)


@app.create
def create(
    name: abi.String,
    url: abi.String,
    enabled: abi.Bool,
    admin: abi.Account,
) -> Expr:
    """
    Initializes application state.
    """

    return Seq(
        app.state.name.set(name.get()),
        app.state.url.set(url.get()),
        app.state.enabled.set(enabled.get()),
        app.state.admin.set(admin.address()),
    )


@app.opt_in
def optin() -> Expr:
    return Seq(
        app.initialize_local_state(Txn.sender()),
        If(
            Txn.sender() == app.state.admin.get(),
            grant_admin_permission(Txn.sender()),
        ),
    )


@Subroutine(return_type=TealType.none)
def grant_admin_permission(account: Expr):
    return Seq(
        (admin_perm := abi.Uint64()).set(Permission.Admin.value),
        app.state.account_permissions[account].grant(admin_perm),
    )


@app.external(authorize=contains_register_key_perm)
def register_keys(
    signing_address: abi.Address,
    encryption_address: abi.Address,
) -> Expr:
    """
    Notes
    -----
    - application account must be prefunded to pay for box storage


    :param signing_address:
    :param encryption_address:
    :return:
    """
    return app.state.keys[signing_address.get()].set(encryption_address.get())
