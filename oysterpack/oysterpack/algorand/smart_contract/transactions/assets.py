from pyteal import TxnField, InnerTxnBuilder, Addr, TxnType, Int, Txn, Expr, Global

from oysterpack.algorand.client.model import Address, AssetID


def transfer(*, receiver: Address, asset_id: AssetID, amount: int) -> list[Expr]:
    """
    Creates an inner transaction to transfer assets from the smart contract to the specified receiver

    :param asset_id: must be in the assets array sent as part of the application call
    """

    exprs = [
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_receiver: Addr(receiver),
                TxnField.asset_amount: Int(amount),
                TxnField.xfer_asset: Txn.assets[asset_id],
            }
        ),
    ]

    return exprs


def optin(asset_id: AssetID) -> list[Expr]:
    """
    Creates an inner transaction to opt-in the smart conract into an asset.

    NOTE: the contract must be pre-funded with ALGO to cover the contract's min-balance

    :param asset_id: must be in the assets array sent as part of the application call
    """
    return [
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_receiver: Global.current_application_address(),
                TxnField.asset_amount: Int(0),
                TxnField.xfer_asset: Txn.assets[asset_id],
            }
        ),
    ]
