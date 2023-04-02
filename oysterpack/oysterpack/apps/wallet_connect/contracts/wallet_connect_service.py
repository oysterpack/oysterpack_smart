"""
Connects apps to wallets for authorizing and signing transactions
"""
from enum import IntEnum
from typing import Final

from beaker import Application
from beaker.lib.storage import BoxMapping
from pyteal.ast import abi

from oysterpack.algorand.application.state.account_permissions import AccountPermissions


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

    # Permissions for managing keys
    RegisterApp = 1 << 1
    UnregisterApp = 1 << 2


app = Application("WalletConnectService", state=WalletConnectServiceState())
