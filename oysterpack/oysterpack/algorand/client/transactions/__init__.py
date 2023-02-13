"""
Provides support to create Algorand transactions.
"""

import functools
from typing import Callable

from algosdk.transaction import SuggestedParams
from algosdk.v2client.algod import AlgodClient
from ulid import ULID

GetSuggestedParams = Callable[[], SuggestedParams]


def create_lease() -> bytes:
    """
    Generates a unique lease, which can be used to set the transaction lease
    :return:
    """
    return str(ULID().to_uuid()).replace("-", "").encode()


def suggested_params_with_flat_flee(
    algod_client: AlgodClient, txn_count: int = 1
) -> SuggestedParams:
    sp = algod_client.suggested_params()
    sp.fee = sp.min_fee * txn_count
    sp.flat_fee = True
    return sp
