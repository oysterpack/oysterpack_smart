"""
Algorand KMD shell
"""
import tomllib
from pathlib import Path
from typing import Any, cast

from algosdk.kmd import KMDClient
from algosdk.transaction import wait_for_confirmation
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.accounts import (
    get_auth_address_callable,
    get_auth_address,
)
from oysterpack.algorand.client.accounts.kmd import (
    WalletSession,
    WalletName,
    WalletPassword,
    Wallet,
    list_wallets,
)
from oysterpack.algorand.client.model import Address, Mnemonic, MicroAlgos, TxnId
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee
from oysterpack.algorand.client.transactions.payment import transfer_algo


class WalletNotConnected(Exception):
    """
    Trying to access a wallet that is not connected
    """


class App:
    """
    KMD shell app
    """

    wallet_session: WalletSession | None = None

    def __init__(self, config: dict[str, Any]):
        def create_algod_client() -> AlgodClient:
            algod_client = AlgodClient(
                algod_token=config["algod"]["token"],
                algod_address=config["algod"]["url"],
            )

            try:
                result = cast(dict[str, Any], algod_client.status())
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
        """
        Constructs a new app instance from the specified TOML config file
        """
        with open(file, "rb") as config_file:
            config = tomllib.load(config_file)
        return cls(config)

    def connect_wallet(self, name: WalletName, password: WalletPassword):
        """
        Connect ot KMD wallet
        """
        self.wallet_session = WalletSession(
            kmd_client=self.kmd_client,
            name=name,
            password=password,
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

    def disconnect_wallet(self):
        """
        Disconnect from KMD wallet
        """
        self.wallet_session = None

    @property
    def connected_wallet(self) -> WalletName | None:
        """
        :return: name of connected wallet
        """
        return self.wallet_session.name if self.wallet_session else None

    def list_wallets(self) -> list[Wallet]:
        """
        :return: list of KMD wallets
        """
        return list_wallets(self.kmd_client)

    def list_wallet_accounts(self) -> list[Address]:
        """
        :return: list of accounts for the connected wallet
        """
        if self.wallet_session is None:
            raise WalletNotConnected

        return self.wallet_session.list_accounts()

    def generate_wallet_account(self) -> Address:
        """
        Generates a new wallet account for the connected wallet.

        :return: address for the new account that was generated
        """
        if self.wallet_session is None:
            raise WalletNotConnected

        return self.wallet_session.generate_key()

    def rekey(
        self, account: Address, to: Address
    ) -> TxnId:  # pylint: disable=invalid-name
        """
        Rekey the account to the specified account.

        Both accounts must exist in the connected wallet
        """
        if self.wallet_session is None:
            raise WalletNotConnected

        return self.wallet_session.rekey(account, to, self.algod_client)

    def rekey_back(self, account: Address) -> TxnId:
        """
        Rekey back the account.
        """
        if self.wallet_session is None:
            raise WalletNotConnected

        return self.wallet_session.rekey_back(account, self.algod_client)

    def get_auth_address(self, account: Address) -> Address:
        """
        :return: authorized address for the specified account
        """
        return get_auth_address(address=account, algod_client=self.algod_client)

    def get_rekeyed_accounts(self) -> dict[Address, Address]:
        """
        :return: all accounts that have been rekeyed in the connected wallet: address -> auth-address
        """
        if self.wallet_session is None:
            raise WalletNotConnected

        rekeyed_accounts: dict[Address, Address] = {}
        for account in self.wallet_session.list_accounts():
            auth_account = self.get_auth_address(account)
            if account != auth_account:
                rekeyed_accounts[account] = auth_account

        return rekeyed_accounts

    def export_key(
        self,
        wallet_name: WalletName,
        wallet_password: WalletPassword,
        account: Address,
    ) -> Mnemonic:
        """
        exports the Mnemonic for the specified wallet account
        """
        wallet_session = WalletSession(
            kmd_client=self.kmd_client,
            name=wallet_name,
            password=wallet_password,
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        return wallet_session.export_key(account)

    def transfer_algo(
        self,
        wallet_name: WalletName,
        wallet_password: WalletPassword,
        sender: Address,
        receiver: Address,
        amount: MicroAlgos,
        note: str | None = None,
    ) -> TxnId:
        """
        Transfers ALGO between 2 accounts in the same wallet
        """

        wallet_session = WalletSession(
            kmd_client=self.kmd_client,
            name=wallet_name,
            password=wallet_password,
            get_auth_addr=get_auth_address_callable(self.algod_client),
        )

        if not wallet_session.contains_key(sender):
            raise AssertionError("sender account does exist in wallet")

        if not wallet_session.contains_key(receiver):
            raise AssertionError("sender account does exist in wallet")

        txn = transfer_algo(
            sender=sender,
            receiver=receiver,
            amount=amount,
            suggested_params=suggested_params_with_flat_flee(self.algod_client),
            note=note,
        )
        signed_txn = wallet_session.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        return TxnId(txid)

    def get_account_info(
        self, account: Address, summary: bool = True
    ) -> dict[str, Any]:
        """
        Returns Algorand account info.

        https://developer.algorand.org/docs/rest-apis/algod/v2/#get-v2accountsaddress

        :param summary: When set to True will exclude asset holdings, application local state, created asset parameters,
                        any created application parameters
        """
        return self.algod_client.account_info(
            account, exclude="all" if summary else None  # type: ignore
        )
