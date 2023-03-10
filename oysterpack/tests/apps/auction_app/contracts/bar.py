from beaker import Application, precompiled
from pyteal import Expr, Seq, InnerTxnBuilder, Txn, InnerTxn
from pyteal.ast import abi

from oysterpack.algorand.application.transactions.application import execute_delete_app
from tests.apps.auction_app.contracts import foo

app = Application("bar")


@app.external
def create_foo(
        *,
        output: abi.Uint64,
) -> Expr:
    return Seq(
        InnerTxnBuilder.ExecuteMethodCall(
            app_id=None,
            method_signature=foo.create.method_signature(),
            args=[Txn.sender()],
            extra_fields=precompiled(foo.app).get_create_config(),  # type: ignore
        ),
        output.set(InnerTxn.created_application_id()),
    )


@app.external
def delete_foo(app: abi.Application) -> Expr:
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
    return execute_delete_app(app.application_id())
