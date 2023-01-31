import algosdk.error
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.model import Address, AssetID, AssetHolding


def get_auth_address(address: Address, algod_client: AlgodClient) -> Address:
    """
    Returns the authorized signing account for the specified address. This only applies to rekeyed acccounts.
    If the account is not rekeyed, then the account is the authorized account, i.e., the account signs for itself.
    """
    account_info = algod_client.account_info(address)
    AUTH_ADDR = "auth-addr"
    if AUTH_ADDR in account_info:
        return Address(account_info[AUTH_ADDR])
    return address


def get_asset_holdings(
    address: Address, algod_client: AlgodClient
) -> list[AssetHolding]:
    account_info = algod_client.account_info(address)
    return [
        AssetHolding.from_data(asset_holding)
        for asset_holding in account_info["assets"]
    ]


def get_asset_holding(
    address: Address, asset_id: AssetID, algod_client: AlgodClient
) -> AssetHolding | None:
    try:
        data = algod_client.account_asset_info(address=address, asset_id=asset_id)[
            "asset-holding"
        ]
    except algosdk.error.AlgodHTTPError as err:
        if err.code == 404:
            return None
        raise
    else:
        return AssetHolding.from_data(data)
