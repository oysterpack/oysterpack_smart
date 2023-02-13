from algosdk.constants import ZERO_ADDRESS
from algosdk.transaction import PaymentTxn

from oysterpack.algorand.client.accounts import Address
from oysterpack.algorand.client.transactions import GetSuggestedParams


def close_account(
    *, account: Address, close_to: Address, suggested_params: GetSuggestedParams
) -> PaymentTxn:
    """
    Closing an account means removing it from the Algorand ledger.

    NOTE: If the account has asset holdings, then the account must first close out those asset holdings before closing out
          the Algorand account completely.


    :param account: account to close
    :param close_to: The remaining ALGO balance is transferred to this account
    :param suggested_params:
    :return: PaymentTxn
    """

    return PaymentTxn(
        sender=account,
        receiver=ZERO_ADDRESS,
        close_remainder_to=close_to,
        amt=0,
        sp=suggested_params,
    )
