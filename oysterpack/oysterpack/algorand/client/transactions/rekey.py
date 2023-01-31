from algosdk.transaction import PaymentTxn

from oysterpack.algorand.client.accounts import Address
from oysterpack.algorand.client.transactions import GetSuggestedParams


def rekey(
    account: Address, rekey_to: Address, suggested_params: GetSuggestedParams
) -> PaymentTxn:
    """
    Creates a transaction to rekey the account to the specified authorized account.

    NOTE: the transaction must be signed by the current authorized account.
    """

    return PaymentTxn(
        sender=account,
        receiver=account,
        amt=0,
        rekey_to=rekey_to,
        sp=suggested_params(),
    )


def rekey_back(account: Address, suggested_params: GetSuggestedParams) -> PaymentTxn:
    """
    Creates a transaction to rekey the account back to itself.

    NOTE: the transaction must be signed by the current authorized account.
    """

    return rekey(account=account, rekey_to=account, suggested_params=suggested_params)
