"""
Provides client side support to construct account rekeying transactions
"""

from algosdk.transaction import PaymentTxn, SuggestedParams

from oysterpack.algorand.client.accounts import Address


def rekey(
    account: Address,
    rekey_to: Address,
    suggested_params: SuggestedParams,
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
        sp=suggested_params,
    )


def rekey_back(account: Address, suggested_params: SuggestedParams) -> PaymentTxn:
    """
    Creates a transaction to rekey the account back to itself.

    NOTE: the transaction must be signed by the current authorized account.
    """

    return rekey(account=account, rekey_to=account, suggested_params=suggested_params)
