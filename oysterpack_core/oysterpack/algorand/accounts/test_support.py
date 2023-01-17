import os

from algosdk import kmd, wallet
from ulid import ULID


def local_kmd_client() -> kmd.KMDClient:
    # sandbox KMD instance
    kmd_token = os.environ.setdefault('KMD_TOKEN', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    kmd_address = os.environ.setdefault('KMD_ADDRESS', 'http://127.0.0.1:4002')
    return kmd.KMDClient(kmd_token, kmd_address)


class KmdTestSupport:
    _kmd_client: kmd.KMDClient = local_kmd_client()

    def _create_test_wallet(self) -> wallet.Wallet:
        """Creates a new emptu wallet and returns a Wallet for testing purposes"""
        wallet_name = wallet_password = str(ULID())
        self._kmd_client.create_wallet(name=wallet_name, pswd=wallet_password)
        return wallet.Wallet(wallet_name=wallet_name, wallet_pswd=wallet_password, kmd_client=self._kmd_client)
