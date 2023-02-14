"""
Provides support for constructing asset related transactions within smart contracts
"""

from typing import cast

from pyteal import TxnField, InnerTxnBuilder, TxnType, Int, Expr, Global
from pyteal.ast import abi


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
    asset: abi.Asset, close_to: abi.Account | abi.Address | Expr | None = None
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
        if isinstance(close_to, Expr):
            return close_to
        if isinstance(close_to, abi.Account):
            return close_to.address()
        if isinstance(close_to, abi.Address):
            return cast(abi.Address, close_to).get()
        raise ValueError(
            f"close_to type must be: abi.Account | abi.Address | Expr | None: {type(close_to)}"
        )

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
    asset: abi.Asset, close_to: abi.Account | abi.Address | Expr | None = None
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
    asset: abi.Asset, close_to: abi.Account | abi.Address | Expr | None = None
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
    *,
    receiver: abi.Account | abi.Address | Expr,
    asset: abi.Asset | Expr,
    amount: abi.Uint64 | Expr,
) -> dict[TxnField, Expr | list[Expr]]:
    """
    Sets fields on inner transaction to transfer assets from the smart contract to the specified receiver
    """

    def asset_receiver() -> Expr:
        if isinstance(receiver, Expr):
            return receiver
        if isinstance(receiver, abi.Account):
            return receiver.address()
        if isinstance(receiver, abi.Address):
            return receiver.get()
        raise ValueError(
            f"receiver type must be: abi.Account | abi.Address | Expr : {type(receiver)}"
        )

    def xfer_asset() -> Expr:
        if isinstance(asset, Expr):
            return asset
        if isinstance(asset, abi.Asset):
            return asset.asset_id()
        raise ValueError(f"asset type must be: abi.Asset | Expr : {type(asset)}")

    def asset_amount() -> Expr:
        if isinstance(amount, Expr):
            return amount
        if isinstance(amount, abi.Uint64):
            return amount.get()
        raise ValueError(f"amount type must be: abi.Uint64 | Expr : {type(amount)}")

    return {
        TxnField.type_enum: TxnType.AssetTransfer,
        TxnField.asset_receiver: asset_receiver(),
        TxnField.asset_amount: asset_amount(),
        TxnField.xfer_asset: xfer_asset(),
        TxnField.fee: Int(0),
    }


def set_transfer_txn_fields(
    receiver: abi.Account | abi.Address | Expr,
    asset: abi.Asset | Expr,
    amount: abi.Uint64 | Expr,
) -> Expr:
    """
    Sets fields on inner transaction to transfer assets from the smart contract to the specified receiver
    """
    return InnerTxnBuilder.SetFields(
        transfer_txn_fields(receiver=receiver, asset=asset, amount=amount)
    )


def execute_transfer(
    receiver: abi.Account | abi.Address | Expr,
    asset: abi.Asset | Expr,
    amount: abi.Uint64 | Expr,
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
