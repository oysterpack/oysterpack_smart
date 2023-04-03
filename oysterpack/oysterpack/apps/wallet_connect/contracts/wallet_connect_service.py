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
from oysterpack.apps.wallet_connect.contracts import wallet_connect_app


class WalletConnectServiceState:
    # registered apps
    # app name -> app ID (WalletConnectApp)
    apps: Final[BoxMapping] = BoxMapping(abi.String, abi.Uint64)

    account_permissions: Final[AccountPermissions] = AccountPermissions()


class Permissions(IntEnum):
    """
    Permissions
    """

    # Admin manages permissions for other accounts
    Admin = 1 << 0

    # Permissions for managing apps
    CreateApp = 1 << 1
    DeleteApp = 1 << 2


app = Application("WalletConnectService", state=WalletConnectServiceState())
account_contains_permissions = account_permissions.account_contains_permissions(app)


@Subroutine(TealType.uint64)
def is_admin(account: Expr):
    return Seq(
        (address := abi.Address()).set(account),
        (perm := abi.Uint64()).set(Int(Permissions.Admin.value)),
        account_contains_permissions(address, perm),
    )


@Subroutine(TealType.uint64)
def contains_create_app_perm(account: Expr):
    return Seq(
        (address := abi.Address()).set(account),
        (perm := abi.Uint64()).set(Int(Permissions.CreateApp.value)),
        account_contains_permissions(address, perm),
    )


app.apply(account_permissions_blueprint, is_admin=is_admin)
app.apply(unconditional_create_approval)


@Subroutine(return_type=TealType.none)
def grant_admin_permission(account: Expr):
    return Seq(
        (admin_perm := abi.Uint64()).set(Permissions.Admin.value),
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


@app.external(authorize=contains_create_app_perm)
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
