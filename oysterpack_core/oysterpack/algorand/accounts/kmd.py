"""
This module is used to KMD wallet-derived Algorand accounts

https://developer.algorand.org/docs/get-details/accounts/create/#wallet-derived-kmd
"""
import weakref
from dataclasses import dataclass
from typing import NewType, Any

from algosdk import kmd, mnemonic, error
from algosdk.wallet import Wallet as KmdWallet

from oysterpack.algorand.accounts.model import Mnemonic

WalletId = NewType('WalletId', str)
WalletName = NewType('WalletName', str)
WalletPassword = NewType('WalletPassword', str)


@dataclass(slots=True)
class Wallet:
    id: WalletId
    name: WalletName


def _to_wallet(data: dict[str, Any]) -> Wallet:
    """Internal helper function convert wallet info returned by the KMD client into a typed Wallet"""
    return Wallet(WalletId(data['id']), WalletName(data['name']))


def list_wallets(kmd_client: kmd.KMDClient) -> list[Wallet]:
    return list(map(_to_wallet, kmd_client.list_wallets()))


def get_wallet(kmd_client: kmd.KMDClient, name: WalletName) -> Wallet | None:
    for wallet in list_wallets(kmd_client):
        if wallet.name == name:
            return wallet

    return None


@dataclass(slots=True)
class WalletAlreadyExistsError(Exception):
    """Raised when trying to create a wallet using a name that already exists"""
    name: WalletName


@dataclass(slots=True)
class WalletDoesNotExistError(Exception):
    """Raised when looking up a wallet for a name that does not exist"""
    name: WalletName


def create_wallet(kmd_client: kmd.KMDClient, name: WalletName, password: WalletPassword) -> Wallet:
    """
    Creates a new wallet using the specified name and password.

    :exception WalletAlreadyExistsError: if a wallet with the same name already exists
    """

    if get_wallet(kmd_client, name): raise WalletAlreadyExistsError(name)

    new_wallet = kmd_client.create_wallet(name=name, pswd=password)
    return _to_wallet(new_wallet)


def recover_wallet(kmd_client: kmd.KMDClient,
                   name: WalletName,
                   password: WalletPassword,
                   master_derivation_key: Mnemonic) -> Wallet:
    """
    Tries to recover a wallet using the specified master derivation key mnemonic.
    The recovered wallet will be empty. Keys will need to be regenerated.

    NOTE: If a wallet with the same master derivation key already exists but different name already exists, then a new
          wallet will be created with the specified name and password. Both wallets will generate the same accounts.

    :exception WalletAlreadyExistsError: if a wallet with the same name already exists
    """

    if get_wallet(kmd_client, name): raise WalletAlreadyExistsError(name)
    recovered_wallet = kmd_client.create_wallet(name=name,
                                                pswd=password,
                                                master_deriv_key=master_derivation_key.to_master_derivation_key())
    return _to_wallet(recovered_wallet)


@dataclass(slots=True)
class InvalidWalletPasswordError(Exception):
    name: WalletName


class KmdError(Exception): pass


class WalletSession:

    def __init__(self, kmd_client: kmd.KMDClient, name: WalletName, password: WalletPassword):
        """
        :exception WalletDoesNotExistError: If the wallet for the specified name does not exist
        """

        if get_wallet(kmd_client, name) is None:
            raise WalletDoesNotExistError(name)

        try:
            self._wallet = KmdWallet(wallet_name=name, wallet_pswd=password, kmd_client=kmd_client)
        except error.KMDHTTPError as err:
            if str(err).find('wrong password') != -1:
                raise InvalidWalletPasswordError(name)
            raise KmdError() from err

        # register a finalizer to release the wallet handle
        weakref.finalize(self, self.__del__)

    def __del__(self):
        # If the wallet session creation failed, then the _wallet attributed will not exist.
        # Thus, check that the _wallet attribute exists before releasing the wallet handle.
        if hasattr(self, '_wallet') and self._wallet.handle:
            self._wallet.release_handle()

    def export_master_derivation_key(self) -> Mnemonic:
        mdk = self._wallet.export_master_derivation_key()
        return Mnemonic.from_word_list(mnemonic.from_master_derivation_key(mdk))
