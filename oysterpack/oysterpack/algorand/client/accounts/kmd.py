"""
This module is used to manage KMD wallet-derived Algorand accounts

https://developer.algorand.org/docs/get-details/accounts/create/#wallet-derived-kmd
"""
from dataclasses import dataclass
from typing import NewType, Any, Callable

from algosdk import kmd, mnemonic
from algosdk.atomic_transaction_composer import TransactionSigner
from algosdk.error import KMDHTTPError
from algosdk.transaction import (
    Transaction,
    SignedTransaction,
    LogicSigTransaction,
    MultisigTransaction,
    wait_for_confirmation,
)
from algosdk.v2client.algod import AlgodClient
from algosdk.wallet import Wallet as KmdWallet

from oysterpack.algorand.client.accounts.error import (
    handle_kmd_client_errors,
    InvalidWalletPasswordError,
    DuplicateWalletNameError,
    WalletAlreadyExistsError,
    WalletDoesNotExistError,
)
from oysterpack.algorand.client.model import Mnemonic, Address
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee
from oysterpack.algorand.client.transactions.rekey import rekey

WalletId = NewType("WalletId", str)
WalletName = NewType("WalletName", str)
WalletPassword = NewType("WalletPassword", str)


@dataclass(slots=True)
class Wallet:
    """
    KMD wallet
    """

    id: WalletId  # pylint: disable=invalid-name
    name: WalletName


def _to_wallet(data: dict[str, Any]) -> Wallet:
    """Internal helper function convert wallet info returned by the KMD client into a typed Wallet"""
    return Wallet(WalletId(data["id"]), WalletName(data["name"]))


def create_kmd_client(
    url: str, token: str, check_connection: bool = True
) -> kmd.KMDClient:
    """
    Creates a KMD client instance that is configured to connect to the specified URL using the specified API token.

    NOTE: KMDClient is a stateless HTTP client. The KMD server can be restarted and the client will continue working.

    :param url: KMD server HTTP URL
    :param token: KMD API token
    :param check_connection: if True, then the KMD client connection is checked before returning it.

    :exception InvalidKmdTokenError: if the KMD API token is invalid
    :exception InvalidKmdUrlError: if the client fails to connect to the server because of a bad URL
    """

    client = kmd.KMDClient(kmd_address=url, kmd_token=token)
    if check_connection:
        check_kmd_client(client)
    return client


@handle_kmd_client_errors
def check_kmd_client(client: kmd.KMDClient) -> None:
    """raises a KmdClientError if the KMD client fails to connect to the KMD server

    :exception InvalidKmdTokenError: if the KMD API token is invalid
    :exception InvalidKmdUrlError: if the client fails to connect to the server because of a bad URL
    """

    client.list_wallets()


def list_wallets(kmd_client: kmd.KMDClient) -> list[Wallet]:
    """
    Returns list of KMD wallets
    """
    return list(map(_to_wallet, kmd_client.list_wallets()))


def get_wallet(kmd_client: kmd.KMDClient, name: WalletName) -> Wallet | None:
    """
    Returns wallet for the specified name.

    :return : None if the wallet does not exist
    """
    for wallet in list_wallets(kmd_client):
        if wallet.name == name:
            return wallet

    return None


def create_wallet(
    kmd_client: kmd.KMDClient, name: WalletName, password: WalletPassword
) -> Wallet:
    """
    Creates a new wallet using the specified name and password.

    :exception WalletAlreadyExistsError: if a wallet with the same name already exists
    """

    if get_wallet(kmd_client, name):
        raise WalletAlreadyExistsError()

    new_wallet = kmd_client.create_wallet(name=name, pswd=password)
    return _to_wallet(new_wallet)


def recover_wallet(
    kmd_client: kmd.KMDClient,
    name: WalletName,
    password: WalletPassword,
    master_derivation_key: Mnemonic,
) -> Wallet:
    """
    Tries to recover a wallet using the specified master derivation key mnemonic.
    The recovered wallet will be empty. Keys will need to be regenerated.

    Notes
    -----
    If a wallet with the same master derivation key already exists but different name already exists, then a new
    wallet will be created with the specified name and password. Both wallets will generate the same accounts.
    KMD wallet passwords cannot be changed. If you lost your wallet password, then you can recover oyur wallet using
    its master derivation key. If you want to use the same name, then you will need to delete the KMD data directory
    (or use a new data directory) and start over.

    :exception WalletAlreadyExistsError: if a wallet with the same name already exists
    """

    if get_wallet(kmd_client, name):
        raise WalletAlreadyExistsError()
    recovered_wallet = kmd_client.create_wallet(
        name=name,
        pswd=password,
        master_deriv_key=master_derivation_key.to_master_derivation_key(),
    )
    return _to_wallet(recovered_wallet)


class WalletSession:
    """
    The user connects to the wallet with a username and password to create an authenticated WalletSession.
    """

    @handle_kmd_client_errors
    def __init__(
        self,
        kmd_client: kmd.KMDClient,
        name: WalletName,
        password: WalletPassword,
        get_auth_addr: Callable[[Address], Address],
    ):
        """

        :param get_auth_addr: used to look up the authorized address for signing transactions

        :exception WalletDoesNotExistError
        :exception InvalidWalletPasswordError
        """

        if get_wallet(kmd_client, name) is None:
            raise WalletDoesNotExistError()

        try:
            self._wallet = KmdWallet(
                wallet_name=name,
                wallet_pswd=password,
                kmd_client=kmd_client,
            )
        except KMDHTTPError as err:
            if str(err).find("wrong password") != -1:
                raise InvalidWalletPasswordError from err
            raise

        self._get_auth_addr = get_auth_addr

    @classmethod
    def from_wallet(
        cls,
        wallet: KmdWallet,
        get_auth_addr: Callable[[Address], Address],
    ) -> "WalletSession":
        """
        Constructs a WalletSession from an existing authenticated wallet

        :param wallet: KMD wallet
        :param get_auth_addr: used when signing transactions to look up the account's authorized signing address.
                              This applies to accounts that have been rekeyed. The authorized account myst be located
                              in the same wallet as the rekeyed account.
        :return:
        """
        return cls(
            kmd_client=wallet.kcl,
            name=WalletName(wallet.name),
            password=WalletPassword(wallet.pswd),
            get_auth_addr=get_auth_addr,
        )

    def __del__(self):
        """
        Ensures that the wallet handle is released when the object is finalized, i.e., garbage collected,
        to prevent resource leaks on the KMD server
        """

        # If the wallet session creation failed, then the _wallet attributed will not exist.
        # Thus, check that the _wallet attribute exists before releasing the wallet handle.
        if hasattr(self, "_wallet") and self._wallet.handle:
            try:
                self._wallet.release_handle()
            except Exception:  # ignore any exceptions
                pass

    @property
    def name(self) -> WalletName:
        """
        :return: wallet name
        """
        return WalletName(self._wallet.name)

    @handle_kmd_client_errors
    def export_master_derivation_key(self) -> Mnemonic:
        """
        Exports the wallets master derivation key in mnemonic form.
        The master derivation key is used to recover the wallet
        """

        return Mnemonic.from_word_list(self._wallet.get_mnemonic())

    @handle_kmd_client_errors
    def rename(self, new_name: WalletName) -> None:
        """
        :param new_name: must not be blank. Surrounding whitespace is stripped.
        :return:

        :exception ValueError: if new_name is blank
        :exception ValueError: if new name is same as current name
        :exception DuplicateWalletNameError: if trying to rename the wallet using a name for a wallet that already exists
        """

        new_name = WalletName(new_name.strip())
        if not new_name:
            raise ValueError("wallet name cannot be blank")
        if new_name == self._wallet.name:
            raise ValueError(
                "new wallet name cannot be the same as the current wallet name"
            )
        if get_wallet(self._wallet.kcl, new_name):
            raise DuplicateWalletNameError()

        self._wallet.rename(new_name)

    @handle_kmd_client_errors
    def list_keys(self) -> list[Address]:
        """
        :return: list of addresses that are registerd in this wallet
        """
        return self._wallet.list_keys()

    @handle_kmd_client_errors
    def contains_key(self, address: Address) -> bool:
        """
        :return: True if the wallet contains the specified address
        """
        return address in self.list_keys()

    @handle_kmd_client_errors
    def generate_key(self) -> Address:
        """
        Generates a new key in this wallet.

        Notes
        -----
        keys generated by the wallet can be recovered when the wallet is recovered.
        """
        return Address(self._wallet.generate_key())

    @handle_kmd_client_errors
    def delete_key(self, address: Address) -> bool:
        """
        :return: true if the account for the specified address was successfully deleted
        """
        return self._wallet.delete_key(address)

    @handle_kmd_client_errors
    def export_key(self, address: Address) -> Mnemonic:
        """
        Exports the private key for the specified address in mnemonic form.

        :param address:
        :return:
        """
        private_key = self._wallet.export_key(address)
        return Mnemonic.from_word_list(mnemonic.from_private_key(private_key))

    @handle_kmd_client_errors
    def sign_transaction(self, txn: Transaction) -> SignedTransaction:
        """
        Rekeyed accounts are handled accordingly. If the transaction sender account has been rekeyed, then the authorized
        account will be used to sign the transaction.

        :exception KeyNotFoundError: if the wallet does not contain the transaction signing account
        """

        signing_address = self._get_auth_addr(Address(txn.sender))
        if signing_address == txn.sender:
            return self._wallet.sign_transaction(txn)

        # TODO: waiting on Algorand bug fix
        # The below code should work and is the preferred method, but currently fails
        # see - https://github.com/algorand/py-algorand-sdk/issues/436
        try:
            self._wallet.automate_handle()
            return self._wallet.kcl.sign_transaction(
                handle=self._wallet.handle,
                password=self._wallet.pswd,
                txn=txn,
                signing_address=signing_address,
            )  # type: ignore
        except KMDHTTPError as err:
            if str(err).index("could not decode request body") != -1:
                # the workaround for the above issue is to export the key and sign the transaction on the client side
                return txn.sign(self._wallet.export_key(signing_address))
            raise

    def rekey(self, account: Address, to: Address, algod_client: AlgodClient):
        """
        Rekey the account to the specified account.

        Notes
        -----
        Both accounts must exist in this wallet.

        :param account: rekey from this account
        :param to: rekey to this account
        :param algod_client: AlgodClient
        """

        for acct in (account, to):
            if not self.contains_key(acct):
                raise AssertionError(f"Wallet does not contain account: {acct}")

        txn = rekey(
            account=account,
            rekey_to=to,
            suggested_params=suggested_params_with_flat_flee(algod_client),
        )
        signed_txn = self.sign_transaction(txn)
        txid = algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client, txid)

    def rekey_back(self, account: Address, algod_client: AlgodClient):
        """
        Rekeys the account back to itself.

        Wallet
        ------
        - The account that it rekeyed to must exist in the same wallet
        """
        self.rekey(account, account, algod_client)


class WalletTransactionSigner(TransactionSigner):
    """
    Signs the transaction using a KMD wallet session
    """

    def __init__(self, wallet: WalletSession):
        self.__wallet = wallet

    def sign_transactions(
        self,
        txn_group: list[Transaction],
        indexes: list[int],
    ) -> list[SignedTransaction | LogicSigTransaction | MultisigTransaction]:
        """

        :param txn_group:
        :param indexes: array of indexes in the atomic transaction group that should be signed
        :return:
        """

        return [self.__wallet.sign_transaction(txn_group[i]) for i in indexes]
