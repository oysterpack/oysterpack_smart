import unittest

from algosdk.transaction import SuggestedParams, OnComplete
from algosdk.v2client.algod import AlgodClient
from beaker import Application, precompiled
from beaker import Authorize
from beaker import sandbox
from beaker.client import ApplicationClient
from beaker.consts import algo
from pyteal import Approve, Log, TxnField, TxnType, Int
from pyteal import Expr, Seq, InnerTxnBuilder, Txn, InnerTxn
from pyteal.ast import abi


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

def execute_delete_app(app_id: Expr) -> Expr:
    """
    Constructs expression to execute a transaction to delete app for the specified app ID.
    """
    return InnerTxnBuilder.Execute(delete_app_txn_fields(app_id))

foo = Application("foo")


@foo.create
def create(seller: abi.Account) -> Expr:  # pylint: disable=arguments-differ
    return Seq(
        Log(seller.address()),
        Approve()
    )


@foo.delete(authorize=Authorize.only_creator())
def delete() -> Expr:
    return Approve()


bar = Application("bar")


@bar.external
def create_foo(
        *,
        output: abi.Uint64,
) -> Expr:
    return Seq(
        InnerTxnBuilder.ExecuteMethodCall(
            app_id=None,
            method_signature=create.method_signature(),
            args=[Txn.sender()],
            extra_fields=precompiled(foo).get_create_config(),  # type: ignore
        ),
        output.set(InnerTxn.created_application_id()),
    )


@bar.external
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

def suggested_params_with_flat_flee(
    algod_client: AlgodClient,
    txn_count: int = 1,
) -> SuggestedParams:
    """
    Returns a suggested txn params using the min flat fee.

    :param txn_count: specifies how many transactions to pay for
    """
    suggested_params = algod_client.suggested_params()
    suggested_params.fee = suggested_params.min_fee * txn_count  # type: ignore
    suggested_params.flat_fee = True
    return suggested_params


class MyTestCase(unittest.TestCase):
    def test_create_delete(self):
        account = sandbox.get_accounts().pop()

        app_client = ApplicationClient(sandbox.get_algod_client(), bar, signer=account.signer)
        app_client.create()
        app_client.fund(1 * algo)

        foo_app_id = app_client.call(create_foo).return_value
        app_client.call(
            delete_foo,
            app=foo_app_id,
            suggested_params=suggested_params_with_flat_flee(
                algod_client=sandbox.get_algod_client(), txn_count=3
            )
        )


if __name__ == '__main__':
    unittest.main()
