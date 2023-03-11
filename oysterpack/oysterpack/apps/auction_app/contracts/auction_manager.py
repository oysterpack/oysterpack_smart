"""
Auction Manager smart contract

Use Cases
---------
- Sellers can create new Auction smart contract instances
  - auction creation fees can be looked up
- Anyone can delete finalized Auctions
- AuctionManager creator can withdraw funds from the treasury

Revenue Model
-------------
Revenue is collected from fees paid by sellers to cover Auction smart contract storage fees.
The storage fees are retained by the Auction Manager as revenue.
"""

from typing import Final

from beaker import Application, precompiled
from beaker.decorators import Authorize
from pyteal import (
    Expr,
    InnerTxnBuilder,
    Txn,
    Seq,
    TxnField,
    Int,
    Assert,
    InnerTxn,
    Global,
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions import payment
from oysterpack.algorand.application.transactions.application import execute_delete_app
from oysterpack.apps.auction_app.contracts import auction as auction_contract
from oysterpack.apps.auction_app.contracts.auction import auction_storage_fees

APP_NAME: Final[str] = "oysterpack.AuctionManager"

app = Application(APP_NAME)


# pylint: disable=invalid-name


@app.create
def create() -> Expr:
    """
    Initializes application state
    """
    return app.initialize_global_state()


@app.external(read_only=True)
def app_name(*, output: abi.String) -> Expr:
    """
    Returns the application name
    """
    return output.set(APP_NAME)


@app.external(read_only=True)
def get_auction_creation_fees(*, output: abi.Uint64) -> Expr:
    """
    Returns the ALGO fees (in microalgos) required to create an Auction.
    """
    return output.set(Int(auction_storage_fees()))


@app.external
def create_auction(
        storage_fees: abi.PaymentTransaction,
        *,
        output: abi.Uint64,
) -> Expr:
    """
    Creates new auction contract instance
    
    :param storage_fees: Auction contract storage fees
    :param output: Auction contract appliction ID
    """
    return Seq(
        Assert(
            storage_fees.get().receiver() == Global.current_application_address(),
            storage_fees.get().amount() == Int(auction_storage_fees()),
        ),
        InnerTxnBuilder.ExecuteMethodCall(
            app_id=None,
            method_signature=auction_contract.create.method_signature(),
            args=[Txn.sender()],
            extra_fields=precompiled(auction_contract.app).get_create_config() | {TxnField.fee: Int(0)},  # type: ignore
        ),
        output.set(InnerTxn.created_application_id()),
    )


@app.external
def delete_finalized_auction(auction: abi.Application) -> Expr:
    """
    Inner Transactions
    ------------------
    1. Close out Auction ALGO account to this contract
    2. Delete the Auction contract

    Notes
    -----
    - Auction contract must have been created by this contract.
    - Auction status must be `Finalized
    - When Auction contract is deleted, its ALGO account is closed out to this contract
    - Transaction fees = 0.003 ALGO

    """
    return execute_delete_app(auction.application_id())


@app.external(authorize=Authorize.only_creator())
def withdraw_algo(amount: abi.Uint64) -> Expr:
    """
    Used by the creator to withdraw available ALGO from the treasury.

    The treasury is the surplus ALGO balance above the contract's min balance.

    Notes
    -----
    - transaction fees = 0.002 ALGO
    """

    return InnerTxnBuilder.Execute(payment.transfer(Txn.sender(), amount.get()))
