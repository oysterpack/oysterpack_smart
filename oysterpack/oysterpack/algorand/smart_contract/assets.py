import pyteal

from oysterpack.algorand.client.model import Address, AssetID


def transfer(*, receiver: Address, asset_id: AssetID, amount: int) -> list[pyteal.Expr]:
    """
    Creates an asset transfer inner transaction

    If sender is not None, then the sender address must be rekeyed to the smart contract address.
    """

    exprs = [
        pyteal.InnerTxnBuilder.Begin(),
        pyteal.InnerTxnBuilder.SetFields(
            {
                pyteal.TxnField.type_enum: pyteal.TxnType.AssetTransfer,
                pyteal.TxnField.asset_receiver: pyteal.Addr(receiver),
                pyteal.TxnField.asset_amount: pyteal.Int(amount),
                # Must be in the assets array sent as part of the application call
                pyteal.TxnField.xfer_asset: pyteal.Txn.assets[asset_id],
            }
        ),
    ]

    return exprs


def optin(asset_id: AssetID) -> list[pyteal.Expr]:
    """
    Creates an inner transaction to opt-in the smart conract into an asset.

    NOTE: the contract must be pre-funded with ALGO to cover the contract's min-balance
    """
    return [
        pyteal.InnerTxnBuilder.Begin(),
        pyteal.InnerTxnBuilder.SetFields(
            {
                pyteal.TxnField.type_enum: pyteal.TxnType.AssetTransfer,
                pyteal.TxnField.asset_receiver: pyteal.Global.current_application_address(),
                pyteal.TxnField.asset_amount: pyteal.Int(0),
                # Must be in the assets array sent as part of the application call
                pyteal.TxnField.xfer_asset: pyteal.Txn.assets[asset_id],
            }
        ),
    ]
