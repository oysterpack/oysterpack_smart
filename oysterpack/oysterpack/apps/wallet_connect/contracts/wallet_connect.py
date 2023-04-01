"""
Connects apps to wallets for authorizing and signing transactions
"""
from beaker import Application


class WalletConnectServiceState:
    pass


app = Application("WalletConnectService")
