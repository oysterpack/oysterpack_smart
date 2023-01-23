from typing import NewType

from algosdk.transaction import PaymentTxn

from oysterpack.algorand.accounts import Address
from oysterpack.algorand.transactions import GetSuggestedParams, create_lease

MicroAlgos = NewType('MicroAlgos', int)


def transfer_algo(
        *, sender: Address,
        receiver: Address,
        amount: MicroAlgos,
        suggested_params: GetSuggestedParams,
        note: str | None = None
) -> PaymentTxn:
    """
    The payment transaction is configured with a lease to protect against from the payment transaction being sent twice.
    """

    return PaymentTxn(
        sender=sender,
        receiver=receiver,
        amt=amount,
        sp=suggested_params(),
        lease=create_lease(),
        note=None if note is None else note.encode()
    )
