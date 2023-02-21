"""
Algorand account related utility functions
"""

from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.model import Address, AssetId, AssetHolding


class AccountDoesNotExist(Exception):
    """
    Raised if the Algorand account does not exist on-chain.
    """


def get_auth_address(address: Address, algod_client: AlgodClient) -> Address:
    """
    Returns the authorized signing account for the specified address. This only applies to rekeyed acccounts.
    If the account is not rekeyed, then the account is the authorized account, i.e., the account signs for itself.
    """

    try:
        account_info = algod_client.account_info(address)
    except AlgodHTTPError as err:
        if err.code == 404:
            raise AccountDoesNotExist from err
        raise
    auth_addr = "auth-addr"
    if auth_addr in account_info:
        return Address(account_info[auth_addr])
    return address


def get_asset_holdings(
    address: Address, algod_client: AlgodClient
) -> list[AssetHolding]:
    """
    Returns asset holdings for the specified Algorand address
    """
    try:
        account_info = algod_client.account_info(address)
    except AlgodHTTPError as err:
        if err.code == 404:
            raise AccountDoesNotExist from err
        raise

    return [
        AssetHolding.from_data(asset_holding)
        for asset_holding in account_info["assets"]
    ]


def get_asset_holding(
    address: Address,
    asset_id: AssetId,
    algod_client: AlgodClient,
) -> AssetHolding | None:
    """
    Returns asset-holding for the specified Algorand address.

    :return : None if the Algorand address does not exist on-chain
    """
    try:
        data = algod_client.account_asset_info(address=address, asset_id=asset_id)
    except AlgodHTTPError as err:
        if err.code == 404:
            return None
        raise

    return AssetHolding.from_data(data)
