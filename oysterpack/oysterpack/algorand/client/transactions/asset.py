"""
Provides client side support for constructing asset related transactions
"""

import algosdk.account
from algosdk.transaction import (
    AssetOptInTxn,
    AssetTransferTxn,
    AssetCreateTxn,
    AssetUpdateTxn,
    AssetCloseOutTxn,
    SuggestedParams,
)

from oysterpack.algorand.client.model import Address, AssetId
from oysterpack.algorand.client.transactions import create_lease


def create(
    *,
    sender: Address,
    suggested_params: SuggestedParams,
    unit_name: str,
    asset_name: str,
    total_base_units: int,
    decimals: int = 0,
    manager: Address | None = None,
    reserve: Address | None = None,
    freeze: Address | None = None,
    clawback: Address | None = None,
    default_frozen: bool | None = None,
    metadata_hash: bytes | None = None,
    url: str | None = None,
    note: bytes | None = None,
) -> AssetCreateTxn:
    """
    Constructs an asset creation transaction.

    https://developer.algorand.org/docs/get-details/asa/#creating-an-asset
    """
    return AssetCreateTxn(
        sender=sender,
        unit_name=unit_name,
        asset_name=asset_name,
        url=url,
        metadata_hash=metadata_hash,
        total=total_base_units,
        decimals=decimals,
        manager=manager,
        reserve=reserve,
        freeze=freeze,
        clawback=clawback,
        default_frozen=default_frozen,
        sp=suggested_params,
        note=note,
        lease=create_lease(),
    )


def update(
    *,
    sender: Address,
    asset_id: AssetId,
    manager: Address | None,
    reserve: Address | None,
    freeze: Address | None,
    clawback: Address | None,
    suggested_params: SuggestedParams,
    note: bytes | None = None,
) -> AssetUpdateTxn:
    """
    Constructs a transaction to update the asset configuration.

    https://developer.algorand.org/docs/get-details/asa/#modifying-an-asset
    """

    return AssetUpdateTxn(
        sender=sender,
        index=asset_id,
        manager=manager if manager is not None else "",
        reserve=reserve if reserve is not None else "",
        freeze=freeze if freeze is not None else "",
        clawback=clawback if clawback is not None else "",
        sp=suggested_params,
        note=note,
        lease=create_lease(),
    )


def opt_in(
    *,
    account: Address,
    asset_id: AssetId,
    suggested_params: SuggestedParams,
    note: bytes | None = None,
) -> AssetOptInTxn:
    """
    Used to construct a transaction to opt in the asset for the specified account.

    https://developer.algorand.org/docs/get-details/asa/#receiving-an-asset
    """

    return AssetOptInTxn(
        sender=account,
        index=asset_id,
        sp=suggested_params,
        note=note,
        lease=create_lease(),
    )


def close_out(
    *,
    account: Address,
    close_to: Address | None = None,
    asset_id: AssetId,
    suggested_params: SuggestedParams,
    note: bytes | None = None,
) -> AssetCloseOutTxn:
    """
    Constructs a  transaction to close out the asset, i.e., opt-out.

    https://developer.algorand.org/docs/get-details/asa/#revoking-an-asset

    :param close_to: any remaining balance is transferred to this account
    """
    return AssetCloseOutTxn(
        sender=account,
        receiver=close_to if close_to else algosdk.account.generate_account()[1],
        index=asset_id,
        sp=suggested_params,
        note=note,
        lease=create_lease(),
    )


def transfer(
    *,
    sender: Address,
    receiver: Address,
    asset_id: AssetId,
    amount: int,
    suggested_params: SuggestedParams,
    note: bytes | None = None,
) -> AssetTransferTxn:
    """
    Constructs an asset transfer transaction.

    https://developer.algorand.org/docs/get-details/asa/#transferring-an-asset
    """
    return AssetTransferTxn(
        sender=sender,
        receiver=receiver,
        index=asset_id,
        amt=amount,
        note=note,
        sp=suggested_params,
        lease=create_lease(),
    )
