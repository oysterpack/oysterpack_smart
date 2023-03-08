"""
Algorand KMD shell
"""
import tomllib
from pathlib import Path
from typing import Any

from algosdk.kmd import KMDClient
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.accounts import get_auth_address_callable
from oysterpack.algorand.client.accounts.kmd import (
    WalletSession,
    WalletName,
    WalletPassword,
)


class App:
    wallet_session: WalletSession | None = None

    def __init__(self, config: dict[str, Any]):
        def create_algod_client() -> AlgodClient:
            algod_client = AlgodClient(
                algod_token=config["algod"]["token"],
                algod_address=config["algod"]["url"],
            )

            try:
                result = algod_client.status()
            except Exception as err:
                raise AssertionError("Failed to connect to Algorand node") from err

            if catchup_time := result["catchup-time"] > 0:
                raise AssertionError(
                    f"Algorand node is not caught up: catchup_time={catchup_time}"
                )

            return algod_client

        def create_kmd_client() -> KMDClient:
            kmd_client = KMDClient(
                kmd_token=config["kmd"]["token"],
                kmd_address=config["kmd"]["url"],
            )
            try:
                kmd_client.list_wallets()
            except Exception as err:
                raise AssertionError("Failed to connect to KMD node") from err

            return kmd_client

        self.algod_client = create_algod_client()
        self.kmd_client = create_kmd_client()
        self.config = config

    @classmethod
    def from_config_file(cls, file: Path) -> "App":
        with open(file, "rb") as f:
            config = tomllib.load(f)
        return cls(config)

    def connect_wallet(self, name: str, password: str):
        self.wallet_session = WalletSession(
            kmd_client=self.kmd_client,
            name=WalletName(name),
            password=WalletPassword(password),
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

    def connected_wallet(self) -> WalletName | None:
        return self.wallet_session.name if self.wallet_session else None
