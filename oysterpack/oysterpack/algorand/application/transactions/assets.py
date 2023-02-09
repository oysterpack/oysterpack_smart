from typing import cast

from pyteal import TxnField, InnerTxnBuilder, TxnType, Int, Expr, Global
from pyteal.ast import abi
from pyteal.ast.abi import make


def optin_txn_fields(asset: abi.Asset) -> dict[TxnField, Expr | list[Expr]]:
    """
    Assembles fields for an inner transaction to opt-in the smart conract into the specified asset.

    NOTES
    -----
    - the contract must be pre-funded with ALGO to cover the contract's min-balance
    - transaction fees must be covered externally
    """
    return {
        TxnField.type_enum: TxnType.AssetTransfer,
        TxnField.asset_receiver: Global.current_application_address(),
        TxnField.asset_amount: Int(0),
        TxnField.xfer_asset: asset.asset_id(),
        TxnField.fee: Int(0),
    }


def set_optin_txn_fields(asset: abi.Asset) -> Expr:
    """
    Sets fields on an inner transaction to opt-in the smart conract into the specified asset.

    NOTES
    -----
    - the contract must be pre-funded with ALGO to cover the contract's min-balance
    - transaction fees must be covered externally
    """
    return InnerTxnBuilder.SetFields(optin_txn_fields(asset))


def execute_optin(asset: abi.Asset) -> Expr:
    """
    Sets fields on an inner transaction to opt-in the smart conract into the specified asset.

    NOTES
    -----
    - the contract must be pre-funded with ALGO to cover the contract's min-balance
    - transaction fees must be covered externally
    """
    return InnerTxnBuilder.Execute(optin_txn_fields(asset))


def optout_txn_fields(
    asset: abi.Asset, close_to: abi.Account | abi.Address | None = None
) -> dict[TxnField, Expr | list[Expr]]:
    """
    Assembles fields for an inner transaction to opt-out the smart contract for the specified asset.

    ::param close_to: defaults to `Global.creator_address()`

    NOTES
    -----
    - transaction fees must be covered externally
    """

    def get_close_to_address() -> Expr:
        if close_to is None:
            return Global.creator_address()
        if type(close_to) is abi.Account:
            address = make(abi.Address)
            address.set(close_to.address())
            return address.get()
        if type(close_to) is abi.Address:
            return cast(abi.Address, close_to).get()
        raise ValueError("close_to type must be: abi.Account | abi.Address | None")

    asset_close_to = get_close_to_address()
    return {
        TxnField.type_enum: TxnType.AssetTransfer,
        TxnField.xfer_asset: asset.asset_id(),
        TxnField.asset_receiver: asset_close_to,
        TxnField.asset_close_to: asset_close_to,
        TxnField.amount: Int(0),
        TxnField.fee: Int(0),
    }


def set_optout_txn_fields(
    asset: abi.Asset, close_to: abi.Account | abi.Address | None = None
) -> Expr:
    """
    Sets fields on an inner transaction to opt-out the smart contract for the specified asset.

    ::param close_to: defaults to `Global.creator_address()`

    NOTES
    -----
    - transaction fees must be covered externally
    """
    return InnerTxnBuilder.SetFields(optout_txn_fields(asset, close_to))


def execute_optout(
    asset: abi.Asset, close_to: abi.Account | abi.Address | None = None
) -> Expr:
    """
    Sets fields on an inner transaction to opt-out the smart conract for the specified asset.

    ::param close_to: defaults to `Global.creator_address()`

    NOTES
    -----
    - transaction fees must be covered externally
    """

    return InnerTxnBuilder.Execute(optout_txn_fields(asset, close_to))


def transfer_txn_fields(
    *, receiver: abi.Account, asset: abi.Asset, amount: abi.Uint64
) -> dict[TxnField, Expr | list[Expr]]:
    """
    Sets fields on inner transaction to transfer assets from the smart contract to the specified receiver
    """
    return {
        TxnField.type_enum: TxnType.AssetTransfer,
        TxnField.asset_receiver: receiver.address(),
        TxnField.asset_amount: amount.get(),
        TxnField.xfer_asset: asset.asset_id(),
    }


def set_transfer_txn_fields(
    *, receiver: abi.Account, asset: abi.Asset, amount: abi.Uint64
) -> Expr:
    """
    Sets fields on inner transaction to transfer assets from the smart contract to the specified receiver
    """
    return InnerTxnBuilder.SetFields(
        transfer_txn_fields(receiver=receiver, asset=asset, amount=amount)
    )


def execute_transfer(
    receiver: abi.Account, asset: abi.Asset, amount: abi.Uint64
) -> Expr:
    """
    Sets fields on an inner transaction to opt-out the smart conract for the specified asset.

    NOTES
    -----
    - transaction fees must be covered externally
    """
    return InnerTxnBuilder.Execute(
        transfer_txn_fields(receiver=receiver, asset=asset, amount=amount)
    )
