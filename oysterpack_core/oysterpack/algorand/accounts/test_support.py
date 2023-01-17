import os

from algosdk import kmd


def local_kmd_client() -> kmd.KMDClient:
    # sandbox KMD instance
    kmd_token = os.environ.setdefault('KMD_TOKEN', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    kmd_address = os.environ.setdefault('KMD_ADDRESS', 'http://127.0.0.1:4002')
    return kmd.KMDClient(kmd_token, kmd_address)


class KmdTestSupport:
    _kmd_client: kmd.KMDClient = local_kmd_client()
