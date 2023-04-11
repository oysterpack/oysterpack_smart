"""
Provides support for constructing application related transactions
"""

from algosdk.transaction import OnComplete
from pyteal import TxnField, TxnType, Int, Expr, InnerTxnBuilder


def delete_app_txn_fields(app_id: Expr) -> dict[TxnField, Expr | list[Expr]]:
    """
    Assembles transaction fields to delete app for the specified app ID
    """
    return {
        TxnField.type_enum: TxnType.ApplicationCall,
        TxnField.application_id: app_id,
        TxnField.on_completion: Int(OnComplete.DeleteApplicationOC.value),
        TxnField.fee: Int(0),
    }


def set_delete_app_txn_fields(app_id: Expr) -> Expr:
    """
    Sets tansaction fields on an inner-transaction to delete app for the specified app ID.
    """
    return InnerTxnBuilder.SetFields(delete_app_txn_fields(app_id))


def execute_delete_app(app_id: Expr) -> Expr:
    """
    Constructs expression to execute a transaction to delete app for the specified app ID.
    """
    return InnerTxnBuilder.Execute(delete_app_txn_fields(app_id))


def optin_app_txn_fields(app_id: Expr) -> dict[TxnField, Expr | list[Expr]]:
    """
    Assembles transaction fields to optin
    """
    return {
        TxnField.type_enum: TxnType.ApplicationCall,
        TxnField.application_id: app_id,
        TxnField.on_completion: Int(OnComplete.OptInOC.value),
        TxnField.fee: Int(0),
    }


def set_optin_app_txn_fields(app_id: Expr) -> Expr:
    """
    Constructs expression to execute a transaction to optin the app for the specified app ID.
    """
    return InnerTxnBuilder.SetFields(optin_app_txn_fields(app_id))


def execute_optin_app(app_id: Expr) -> Expr:
    """
    Constructs expression to execute a transaction to optin the app for the specified app ID.
    """
    return InnerTxnBuilder.Execute(optin_app_txn_fields(app_id))
