"""
Unit tests depend on a local sandbox running.
"""

import functools
import logging
from logging import Logger
from typing import Callable, Final

from algosdk import kmd, wallet
from algosdk.atomic_transaction_composer import TransactionSigner
from algosdk.transaction import wait_for_confirmation
from algosdk.v2client.algod import AlgodClient
from beaker import sandbox, Application
from beaker.client import ApplicationClient
from beaker.sandbox.kmd import get_sandbox_default_wallet
from ulid import ULID

from oysterpack.algorand.client.accounts import get_auth_address
from oysterpack.algorand.client.accounts.kmd import (
    WalletTransactionSigner,
    WalletSession,
)
from oysterpack.algorand.client.model import Address, AssetId
from oysterpack.algorand.client.transactions import assets as client_assets
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

    def sandbox_default_wallet_transaction_signer(self) -> WalletTransactionSigner:
        return WalletTransactionSigner(
            WalletSession.from_wallet(self.sandbox_default_wallet, self.get_auth_addr())
        )

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

        if signer is None:
            account = sandbox.get_accounts().pop()
            signer = account.signer
        return ApplicationClient(
            client=sandbox.get_algod_client(),
            app=app,
            sender=sender,
            signer=signer,
        )

    def create_test_asset(self, asset_name: str) -> tuple[AssetId, Address]:
        """
        Creates a new asset using the first account in the sandbox default wallet as the administrative accounts.

        Returns (AssetId, manager account address)
        """

        def metadata_hash() -> bytes:
            import hashlib

            m = hashlib.sha256()
            m.update(b"asset metadata")
            return m.digest()

        sender = Address(sandbox.get_accounts().pop().address)
        manager = reserve = freeze = clawback = sender
        total_base_units = 1_000_000_000_000_000
        decimals = 6
        unit_name = asset_name
        url = "https://meld.gold/"
        txn = client_assets.create(
            sender=sender,
            manager=manager,
            reserve=reserve,
            freeze=freeze,
            clawback=clawback,
            asset_name=asset_name,
            unit_name=unit_name,
            url=url,
            metadata_hash=metadata_hash(),
            total_base_units=total_base_units,
            decimals=decimals,
            suggested_params=sandbox.get_algod_client().suggested_params,
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = sandbox.get_algod_client().send_transaction(signed_txn)
        tx_info = wait_for_confirmation(
            algod_client=sandbox.get_algod_client(), txid=txid, wait_rounds=4
        )

        return AssetId(tx_info["asset-index"]), Address(manager)
