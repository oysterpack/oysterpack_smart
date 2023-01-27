"""
Unit tests depend on a local sandbox running.
"""

import functools
from typing import Callable, Final

from algosdk import kmd, wallet
from algosdk.v2client.algod import AlgodClient
from beaker import sandbox
from ulid import ULID

from oysterpack.algorand.accounts import get_auth_address
from oysterpack.algorand.model import Address


def sandbox_kmd_client() -> kmd.KMDClient:
    return kmd.KMDClient(
        kmd_token=sandbox.kmd.DEFAULT_KMD_TOKEN,
        kmd_address=sandbox.kmd.DEFAULT_KMD_ADDRESS,
    )


def get_sandbox_default_wallet() -> wallet.Wallet:
    return wallet.Wallet(
        wallet_name=sandbox.kmd.DEFAULT_KMD_WALLET_NAME,
        wallet_pswd=sandbox.kmd.DEFAULT_KMD_WALLET_PASSWORD,
        kmd_client=sandbox_kmd_client(),
    )


class AlgorandTestSupport:
    kmd_client: Final[kmd.KMDClient] = sandbox_kmd_client()
    algod_client: Final[AlgodClient] = sandbox.get_algod_client()
    sandbox_default_wallet: Final[wallet.Wallet] = get_sandbox_default_wallet()

    def get_auth_addr(self) -> Callable[[Address], Address]:
        return functools.partial(get_auth_address, algod_client=self.algod_client)

    def create_test_wallet(self) -> wallet.Wallet:
        """Creates a new emptu wallet and returns a Wallet for testing purposes"""
        wallet_name = wallet_password = str(ULID())
        self.kmd_client.create_wallet(name=wallet_name, pswd=wallet_password)
        return wallet.Wallet(
            wallet_name=wallet_name,
            wallet_pswd=wallet_password,
            kmd_client=self.kmd_client,
        )
