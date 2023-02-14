"""
Provides support for constructing payment related transactions within smart contracts
"""

from pyteal import TxnField, TxnType, Int, Expr


def close_out(close_remainder_to: Expr) -> dict[TxnField, Expr | list[Expr]]:
    """
    Constructs a payment transaction to close out the smart contract account.
    """
    return {
        TxnField.type_enum: TxnType.Payment,
        TxnField.receiver: close_remainder_to,
        TxnField.close_remainder_to: close_remainder_to,
        TxnField.amount: Int(0),
        TxnField.fee: Int(0),
    }


def transfer(receiver: Expr, amount: Expr) -> dict[TxnField, Expr | list[Expr]]:
    """
    Constructs a payment transaction to transfer the specified ALGO amount to the specified receiver.
    """
    return {
        TxnField.type_enum: TxnType.Payment,
        TxnField.receiver: receiver,
        TxnField.amount: amount,
        TxnField.fee: Int(0),
    }
