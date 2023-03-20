"""
Provides support to create Algorand transactions.
"""
from base64 import b64decode
from typing import Callable

from algosdk import constants
from algosdk.encoding import msgpack_encode
from algosdk.transaction import SuggestedParams, Transaction
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
        algod_client: AlgodClient,
        txn_count: int = 1,
) -> SuggestedParams:
    """
    Returns a suggested txn params using the min flat fee.

    :param txn_count: specifies how many transactions to pay for
    """
    suggested_params = algod_client.suggested_params()
    suggested_params.fee = suggested_params.min_fee * txn_count  # type: ignore
    suggested_params.flat_fee = True
    return suggested_params


def transaction_message_for_signing(txn: Transaction) -> bytes:
    """
    :return: transaction message used for signing
    """
    return constants.txid_prefix + b64decode(msgpack_encode(txn))
