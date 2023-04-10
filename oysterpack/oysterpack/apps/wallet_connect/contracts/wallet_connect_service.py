"""
Connects apps to wallets for authorizing and signing transactions
"""
from enum import IntEnum
from typing import Final

from beaker import Application, precompiled, unconditional_create_approval
from beaker.lib.storage import BoxMapping
from pyteal import (
    Expr,
    Seq,
    Int,
    Subroutine,
    TealType,
    If,
    Global,
    InnerTxn,
    InnerTxnBuilder,
    TxnField,
    Txn,
    Itob,
    Assert,
    Not,
)
from pyteal.ast import abi

from oysterpack.algorand.application.state import account_permissions
from oysterpack.algorand.application.state.account_permissions import (
    AccountPermissions,
    account_permissions_blueprint,
)
from oysterpack.apps.wallet_connect.contracts import wallet_connect_app, wallet_connect_account

WalletConnectAppName = abi.String
WalletConnectAppId = abi.Uint64

WalletConnectAccountAddress = abi.Address
WalletConnectAccountAppId = abi.Uint64


class WalletConnectServiceState:
    # registered apps
    # app name -> app ID (WalletConnectApp)
    apps: Final[BoxMapping] = BoxMapping(WalletConnectAppName, WalletConnectAppId)

    # registered accounts
    # WalletConnectAccount.account -> app ID (WalletConnectAccount)
    accounts: Final[BoxMapping] = BoxMapping(WalletConnectAccountAddress, WalletConnectAccountAppId)

    account_permissions: Final[AccountPermissions] = AccountPermissions()


class Permission(IntEnum):
    """
    Permissions
    """

    # Admin manages permissions for other accounts
    Admin = 1 << 0

    # Permissions for managing apps
    CreateApp = 1 << 1
    DeleteApp = 1 << 2

    # Permissions for managing accounts
    CreateAccount = 1 << 3
    UpdateAccount = 1 << 4
    DeleteAccount = 1 << 5


app = Application("WalletConnectService", state=WalletConnectServiceState())
account_contains_permissions = account_permissions.account_contains_permissions(app)


def contains_permission(account: Expr, permission: Permission) -> Expr:
    return Seq(
        (address := abi.Address()).set(account),
        (perm := abi.Uint64()).set(Int(permission.value)),
        account_contains_permissions(address, perm),
    )


@Subroutine(TealType.uint64)
def is_admin(account: Expr) -> Expr:
    return contains_permission(account, Permission.Admin)


@Subroutine(TealType.uint64)
def can_create_app(account: Expr)-> Expr:
    return contains_permission(account, Permission.CreateApp)

@Subroutine(TealType.uint64)
def can_create_account(account: Expr)-> Expr:
    return contains_permission(account, Permission.CreateAccount)


app.apply(account_permissions_blueprint, is_admin=is_admin)
app.apply(unconditional_create_approval)


@Subroutine(return_type=TealType.none)
def grant_admin_permission(account: Expr):
    return Seq(
        (admin_perm := abi.Uint64()).set(Permission.Admin.value),
        app.state.account_permissions[account].grant(admin_perm),
    )


@app.opt_in
def optin() -> Expr:
    return Seq(
        app.initialize_local_state(Txn.sender()),
        If(
            Txn.sender() == Global.creator_address(),
            grant_admin_permission(Txn.sender()),
        ),
    )


@app.external(authorize=can_create_app)
def create_app(
        name: abi.String,
        url: abi.String,
        enabled: abi.Bool,
        admin: abi.Account,
        *,
        output: abi.Uint64,
) -> Expr:
    return Seq(
        Assert(Not(app.state.apps[name.get()].exists())),
        InnerTxnBuilder.ExecuteMethodCall(
            app_id=None,
            method_signature=wallet_connect_app.create.method_signature(),
            args=[
                name,
                url,
                enabled,
                admin,
            ],
            extra_fields=precompiled(wallet_connect_app.app).get_create_config()
                         | {TxnField.fee: Int(0)},
            # type: ignore
        ),
        app.state.apps[name.get()].set(Itob(InnerTxn.created_application_id())),
        output.set(InnerTxn.created_application_id()),
    )


@app.external(authorize=can_create_account)
def create_account(
        account: abi.Account,
        *,
        output: abi.Uint64,
) -> Expr:
    return Seq(
        Assert(Not(app.state.accounts[account.address()].exists())),
        InnerTxnBuilder.ExecuteMethodCall(
            app_id=None,
            method_signature=wallet_connect_account.create.method_signature(),
            args=[account],
            extra_fields=precompiled(wallet_connect_account.application).get_create_config()
                         | {TxnField.fee: Int(0)},
            # type: ignore
        ),
        app.state.apps[account.address()].set(Itob(InnerTxn.created_application_id())),
        output.set(InnerTxn.created_application_id()),
    )
