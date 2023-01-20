from algosdk.transaction import PaymentTxn
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.accounts.account import Address


def rekey_account_transaction(account: Address, rekey_to: Address, algod_client: AlgodClient) -> PaymentTxn:
    """
    Creates a transaction to rekey the account to the specified authorized account.

    NOTE: the transaction must be signed by the current authorized account.
    """

    return PaymentTxn(sender=account,
                      receiver=account,
                      amt=0,
                      sp=algod_client.suggested_params(),
                      rekey_to=rekey_to)


def rekey_account_back_transaction(account: Address, algod_client: AlgodClient) -> PaymentTxn:
    """
    Creates a transaction to rekey the account back to itself.

    NOTE: the transaction must be signed by the current authorized account.
    """

    return rekey_account_transaction(account=account, rekey_to=account, algod_client=algod_client)
