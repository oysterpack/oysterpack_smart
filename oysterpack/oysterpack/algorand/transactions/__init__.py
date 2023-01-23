"""
Provides support to create Algorand transactions.
"""

import functools
from typing import Callable

from algosdk.constants import MIN_TXN_FEE
from algosdk.transaction import SuggestedParams
from algosdk.v2client.algod import AlgodClient

GetSuggestedParams = Callable[[], SuggestedParams]

from ulid import ULID


def create_lease() -> bytes:
    """
    Generates a unique lease, which can be used to set the transaction lease
    :return:
    """
    return str(ULID().to_uuid()).replace('-', '').encode()


def suggested_params_with_min_flat_flee(algod_client: AlgodClient) -> SuggestedParams:
    params = algod_client.suggested_params()
    params.flat_fee = True
    params.fee = MIN_TXN_FEE
    return params


class GetSuggestedParamsFactory:

    @staticmethod
    def create_with_min_flat_fee(algod_client: AlgodClient) -> GetSuggestedParams:
        """
        Returns a GetSuggestedParams function that creates a SuggestedParams with a flat fee set to the current Algorand
        minimum transaction fee.
        """
        return functools.partial(suggested_params_with_min_flat_flee, algod_client)
