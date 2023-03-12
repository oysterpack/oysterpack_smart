import unittest
from base64 import b64decode, b64encode
from typing import cast

from algosdk.error import AlgodHTTPError
from beaker import (
    Application,
    Authorize,
    sandbox, precompiled,
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
    Txn, )
from pyteal.ast import abi

from tests.algorand.test_support import AlgorandTestCase


def verify_app(app_client: ApplicationClient):
    """
    Verifies that the app ID references an app whose program binaries matches the app referenced by the ApplicationClient.

    :raise AssertionError: if code does not match
    """

    def diff(prog_1: str, prog_2: str) -> str:
        if len(prog_1) != len(prog_2):
            return f"program lengths do not match: {len(prog_1)} != {len(prog_2)}"

        diffs = ""
        for i, (a, b) in enumerate(zip(prog_1, prog_2)):
            if a != b:
                diffs += "^"
            else:
                diffs += " "

        return f"""
        {prog_1}
        {prog_2}
        {diffs}
        """

    try:
        app = app_client.client.application_info(app_client.app_id)
        approval_program = b64decode(app["params"]["approval-program"])
        clear_state_program = b64decode(app["params"]["clear-state-program"])

        if approval_program != app_client.approval.raw_binary:
            cause = diff(
                b64encode(approval_program).decode(),
                b64encode(cast(bytes, app_client.approval.raw_binary)).decode(),
            )
            raise AssertionError(
                f"Invalid app ID - approval program does not match: {cause}"
            )

        if clear_state_program != app_client.clear.raw_binary:
            cause = diff(
                b64encode(clear_state_program).decode(),
                b64encode(cast(bytes, app_client.clear.raw_binary)).decode(),
            )
            raise AssertionError(
                f"Invalid app ID - clear program does not match: {cause}"
            )
    except AlgodHTTPError as err:
        if err.code == 404:
            raise AssertionError("Invalid app ID") from err
        raise err


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


@bar.delete(authorize=Authorize.only_creator())  # IF YOU COMMENT THIS OUT THEN THE TEST PASSES ???
def delete() -> Expr:
    return Seq(
        # assert that the app has opted out of all assets
        total_assets := AccountParam.totalAssets(
            Global.current_application_address()
        ),
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
def create_bar(*,output: abi.Uint64,
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

        foo_id = foo_client.create()
        foo_client.fund(1_000_000)

        bar_app_id = foo_client.call(create_bar).return_value
        print("bar_app_id=", bar_app_id)

        bar_client = ApplicationClient(sandbox.get_algod_client(), bar, app_id=bar_app_id, signer=account.signer)
        verify_app(bar_client)

    def test_create_bar_directly(self):
        account = sandbox.get_accounts().pop()

        bar_client = ApplicationClient(sandbox.get_algod_client(), bar, signer=account.signer)
        bar_app_id = bar_client.create(owner=account.address)
        print("bar_app_id=", bar_app_id)

        verify_app(bar_client)


if __name__ == "__main__":
    unittest.main()
