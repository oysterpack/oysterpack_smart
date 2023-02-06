"""
Unit tests depend on a local sandbox running.
"""

import functools
import logging
from logging import Logger
from typing import Callable, Final

from algosdk import kmd, wallet
from algosdk.atomic_transaction_composer import TransactionSigner
from algosdk.v2client.algod import AlgodClient
from beaker import sandbox, Application
from beaker.client import ApplicationClient
from beaker.sandbox.kmd import get_sandbox_default_wallet
from ulid import ULID

from oysterpack.algorand.client.accounts import get_auth_address
from oysterpack.algorand.client.model import Address
from oysterpack.core.logging import configure_logging

configure_logging(level=logging.INFO)


class AlgorandTestSupport:
    kmd_client: Final[kmd.KMDClient] = sandbox.kmd.get_client()
    algod_client: Final[AlgodClient] = sandbox.get_algod_client()
    sandbox_default_wallet: Final[wallet.Wallet] = get_sandbox_default_wallet()

    def get_logger(self, name: str) -> Logger:
        return logging.getLogger(f"{self.__class__.__name__}.{name}")

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

    @staticmethod
    def sandbox_application_client(
        app: Application,
        sender: Address | None = None,
        signer: TransactionSigner | None = None,
    ) -> ApplicationClient:
        """
        :param app: Application instance
        :return: ApplicationClient using the default sandbox wallet account as the sender and signer
        """
        account = sandbox.get_accounts().pop()
        return ApplicationClient(
            client=sandbox.get_algod_client(),
            app=app,
            sender=sender if sender else account.address,
            signer=signer if signer else account.signer,
        )
