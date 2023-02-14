"""
Provides support for constructing and validating with payment transactions from with a smart contract.
"""

from pyteal import Global, Txn
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


def is_expected_receiver(txn: abi.PaymentTransaction, address: abi.Address) -> Expr:
    """
    :return: True if the payment receiver matches the specified address
    """
    return txn.get().receiver() == address.get()


def is_current_application_receiver(txn: abi.PaymentTransaction) -> Expr:
    """
    :return: True if the payment receiver is the current smart contract account.
    """
    return txn.get().receiver() == Global.current_application_address()


def is_txn_sender(txn: abi.PaymentTransaction) -> Expr:
    """
    :return: True if the payment sender is the same as the transaction sender
    """
    return txn.get().sender() == Txn.sender()
