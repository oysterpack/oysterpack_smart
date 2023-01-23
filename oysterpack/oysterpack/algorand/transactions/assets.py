import algosdk.account
from algosdk.transaction import AssetOptInTxn, AssetTransferTxn, AssetCreateTxn, AssetUpdateTxn, AssetCloseOutTxn

from oysterpack.algorand.model import Address, AssetID
from oysterpack.algorand.transactions import GetSuggestedParams, create_lease


def create(
        *, sender: Address,
        suggested_params: GetSuggestedParams,
        unit_name: str,
        asset_name: str,
        url: str,
        total_base_units: int,
        decimals: int = 0,
        manager: Address | None = None,
        reserve: Address | None = None,
        freeze: Address | None = None,
        clawback: Address | None = None,
        default_frozen: bool = False,
        metadata_hash: bytes | None = None
) -> AssetCreateTxn:
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
        sp=suggested_params(),
        lease=create_lease()
    )


def update(
        *, sender: Address,
        asset_id: AssetID,
        manager: Address | None,
        reserve: Address | None,
        freeze: Address | None,
        clawback: Address | None,
        suggested_params: GetSuggestedParams
) -> AssetUpdateTxn:
    """
    A Reconfiguration Transaction is issued by the asset manager to change the configuration of an already created asset.
    """

    return AssetUpdateTxn(
        sender=sender,
        index=asset_id,
        manager=manager if manager is not None else '',
        reserve=reserve if reserve is not None else '',
        freeze=freeze if freeze is not None else '',
        clawback=clawback if clawback is not None else '',
        sp=suggested_params(),
        lease=create_lease()
    )


def opt_in(
        *, account: Address,
        asset_id: AssetID,
        suggested_params: GetSuggestedParams
) -> AssetOptInTxn:
    return AssetOptInTxn(
        sender=account,
        index=asset_id,
        sp=suggested_params(),
        lease=create_lease()
    )


def close_out(
        *, account: Address,
        close_to: Address | None = None,
        asset_id: AssetID,
        suggested_params: GetSuggestedParams
) -> AssetCloseOutTxn:
    return AssetCloseOutTxn(
        sender=account,
        receiver=close_to if close_to else algosdk.account.generate_account()[1],
        index=asset_id,
        sp=suggested_params(),
        lease=create_lease()
    )


def transfer(
        *, sender: Address,
        receiver: Address,
        asset_id: AssetID,
        amount: int,
        suggested_params: GetSuggestedParams,
        note: str | None = None
) -> AssetTransferTxn:
    return AssetTransferTxn(
        sender=sender,
        receiver=receiver,
        index=asset_id,
        amt=amount,
        note=None if note is None else note.encode(),
        sp=suggested_params(),
        lease=create_lease()
    )
