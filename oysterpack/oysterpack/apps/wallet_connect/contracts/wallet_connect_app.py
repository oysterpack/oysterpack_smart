"""
App contract
"""
from enum import IntEnum
from typing import Final

from beaker import Application, GlobalStateValue
from pyteal import Expr, TealType

from oysterpack.algorand.application.state.account_permissions import AccountPermissions


class AppState:
    """
    WalletConnectApp state
    """

    name: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        descr="application name",
        static=True,
    )

    version: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        descr="application version",
        static=True,
    )

    url: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        descr="application URL",
        static=True,
    )

    account_permissions: Final[AccountPermissions] = AccountPermissions()


class Permissions(IntEnum):
    Admin = 1 << 0
    Operator = 1 << 1


app = Application("WalletConnectApp", state=AppState())


@app.external()
def create() -> Expr:
    """
    Grants the
    """
    raise NotImplementedError()
