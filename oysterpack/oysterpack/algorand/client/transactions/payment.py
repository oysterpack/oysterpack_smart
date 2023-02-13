from algosdk.transaction import PaymentTxn

from oysterpack.algorand.client.accounts import Address
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions import SuggestedParams, create_lease


def transfer_algo(
    *,
    sender: Address,
    receiver: Address,
    amount: MicroAlgos,
    suggested_params: SuggestedParams,
    note: str | None = None
) -> PaymentTxn:
    """
    The payment transaction is configured with a lease to protect against from the payment transaction being sent twice.
    """

    return PaymentTxn(
        sender=sender,
        receiver=receiver,
        amt=amount,
        sp=suggested_params,
        lease=create_lease(),
        note=None if note is None else note.encode(),
    )
