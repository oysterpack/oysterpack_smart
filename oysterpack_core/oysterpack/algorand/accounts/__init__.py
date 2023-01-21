from typing import Any

from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.models.asset_holding import AssetHolding

from oysterpack.algorand.accounts.model import Address, AssetID


def get_auth_address(address: Address, algod_client: AlgodClient) -> Address:
    """
    Returns the authorized signing account for the specified address. This only applies to rekeyed acccounts.
    If the account is not rekeyed, then the account is the authorized account, i.e., the account signs for itself.
    """
    account_info = algod_client.account_info(address)
    AUTH_ADDR = 'auth-addr'
    if AUTH_ADDR in account_info:
        return Address(account_info[AUTH_ADDR])
    return address


def get_asset_holdings(address: Address, algod_client: AlgodClient) -> list[AssetHolding]:
    account_info = algod_client.account_info(address)

    def to_asset_holding(data: dict[str, Any]) -> AssetHolding:
        return AssetHolding(
            amount=data['amount'],
            asset_id=data['asset-id'],
            creator=data['creator'],
            is_frozen=data['is-frozen']
        )

    return [to_asset_holding(asset_holding) for asset_holding in account_info['assets']]


def get_asset_holding(address: Address, asset_id: AssetID, algod_client: AlgodClient) -> AssetHolding | None:
    for asset_holding in get_asset_holdings(address, algod_client):
        if asset_holding.asset_id == asset_id:
            return asset_holding

    return None
