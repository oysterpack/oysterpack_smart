from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.accounts.model import Address


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
