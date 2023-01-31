from pyteal import Global
from pyteal.ast import abi, Expr, Not, And


def is_rekeying_account(txn: abi.PaymentTransaction) -> Expr:
    """
    Returns true if the transaction is rekeying the account
    """
    return txn.get().rekey_to() != Global.zero_address()


def is_closing_account(txn: abi.PaymentTransaction) -> Expr:
    """
    Returns true of the transaction is closing the account.
    """
    return txn.get().close_remainder_to() != Global.zero_address()


def is_payment_only(txn: abi.PaymentTransaction) -> Expr:
    """
    Returns true if the transaction is not rekeying and not closing the account.
    """
    return And(Not(is_rekeying_account(txn)), Not(is_closing_account(txn)))
