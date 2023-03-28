import unittest

from beaker import (
    Application,
    Authorize,
    sandbox,
    precompiled,
)
from beaker.client import ApplicationClient
from pyteal import (
    Approve,
    TxnField,
    TxnType,
    Int,
    Expr,
    Global,
    Seq,
    AccountParam,
    Assert,
    InnerTxnBuilder,
    InnerTxn,
    Txn,
)
from pyteal.ast import abi

from oysterpack.apps.client import verify_app
from tests.algorand.test_support import AlgorandTestCase


def close_out_account(close_remainder_to: Expr) -> dict[TxnField, Expr | list[Expr]]:
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


bar = Application("Bar")


@bar.create
def create(owner: abi.Account) -> Expr:
    return Approve()


@bar.delete(authorize=Authorize.only_creator())
def delete() -> Expr:
    return Seq(
        # assert that the app has opted out of all assets
        total_assets := AccountParam.totalAssets(Global.current_application_address()),
        Assert(total_assets.value() == Int(0)),
        # close out ALGO balance to the creator
        InnerTxnBuilder.Execute(close_out_account(Global.creator_address())),
    )


@bar.external(read_only=True)
def app_name(*, output: abi.String) -> Expr:
    """
    Returns the application name
    """
    return output.set(bar.name)


@bar.external
def do_bar() -> Expr:
    return Approve()


foo = Application("Foo")


@foo.external
def create_bar(
    *,
    output: abi.Uint64,
) -> Expr:
    return Seq(
        InnerTxnBuilder.ExecuteMethodCall(
            app_id=None,
            method_signature=create.method_signature(),
            args=[Txn.sender()],
            extra_fields=precompiled(bar).get_create_config(),
        ),
        output.set(InnerTxn.created_application_id()),
    )


class MyTestCase(AlgorandTestCase):
    def test_create_via_foo(self):
        account = sandbox.get_accounts().pop()
        foo_client = ApplicationClient(
            sandbox.get_algod_client(), foo, signer=account.signer
        )

        foo_client.create()
        foo_client.fund(1_000_000)

        bar_app_id = foo_client.call(create_bar).return_value
        print("bar_app_id=", bar_app_id)

        bar_client = ApplicationClient(
            sandbox.get_algod_client(), bar, app_id=bar_app_id, signer=account.signer
        )
        verify_app(bar_client)

    def test_create_bar_directly(self):
        account = sandbox.get_accounts().pop()

        bar_client = ApplicationClient(
            sandbox.get_algod_client(), bar, signer=account.signer
        )
        bar_app_id = bar_client.create(owner=account.address)
        print("bar_app_id=", bar_app_id)

        verify_app(bar_client)


if __name__ == "__main__":
    unittest.main()
