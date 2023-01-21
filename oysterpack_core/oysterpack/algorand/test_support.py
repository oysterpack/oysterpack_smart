"""
Unit tests depend on a local sandbox running.
"""

import functools
import os
from typing import Callable

from algosdk import kmd, wallet
from algosdk.v2client.algod import AlgodClient
from ulid import ULID

from oysterpack.algorand.accounts import get_auth_address
from oysterpack.algorand.accounts.model import Address


def local_kmd_client() -> kmd.KMDClient:
    # sandbox KMD instance
    token = os.environ.setdefault('KMD_TOKEN', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    address = os.environ.setdefault('KMD_ADDRESS', 'http://127.0.0.1:4002')
    return kmd.KMDClient(kmd_token=token, kmd_address=address)


def local_algod_client() -> AlgodClient:
    # sandbox algod instance
    token = os.environ.setdefault('ALGOD_TOKEN', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    address = os.environ.setdefault('ALGOD_ADDRESS', 'http://127.0.0.1:4001')
    return AlgodClient(algod_token=token, algod_address=address)


class AlgorandTestSupport:
    kmd_client: kmd.KMDClient = local_kmd_client()
    algod_client: AlgodClient = local_algod_client()

    SANDBOX_DEFAULT_WALLET_NAME = 'unencrypted-default-wallet'
    sandbox_default_wallet = wallet.Wallet(wallet_name=SANDBOX_DEFAULT_WALLET_NAME,
                                           wallet_pswd='',
                                           kmd_client=local_kmd_client())

    def get_auth_addr(self) -> Callable[[Address], Address]:
        return functools.partial(get_auth_address, algod_client=self.algod_client)

    def create_test_wallet(self) -> wallet.Wallet:
        """Creates a new emptu wallet and returns a Wallet for testing purposes"""
        wallet_name = wallet_password = str(ULID())
        self.kmd_client.create_wallet(name=wallet_name, pswd=wallet_password)
        return wallet.Wallet(wallet_name=wallet_name, wallet_pswd=wallet_password, kmd_client=self.kmd_client)
