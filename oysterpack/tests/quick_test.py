import unittest
from typing import Final

from beaker import (
    Application,
    external,
    AppPrecompile,
    create,
    sandbox,
)
from beaker.application import get_method_signature
from beaker.client import ApplicationClient
from pyteal import (
    Approve,
    Expr,
    Seq,
    InnerTxnBuilder,
    InnerTxn,
    Txn,
)
from pyteal.ast import abi

from oysterpack.apps.client import verify_app_id
from tests.algorand.test_support import AlgorandTestCase


class Bar(Application):
    @create
    def create(self, owner: abi.Account) -> Expr:
        return Approve()


class Foo(Application):
    bar: Final[AppPrecompile] = AppPrecompile(Bar())

    @external
    def create_bar(
            self,
            *,
            output: abi.Uint64,
    ) -> Expr:
        return Seq(
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=None,
                method_signature=get_method_signature(Bar.create),
                args=[Txn.sender()],
                extra_fields=self.bar.get_create_config(),
            ),
            output.set(InnerTxn.created_application_id()),
        )


class MyTestCase(AlgorandTestCase):
    def test_app_verification(self):
        account = sandbox.get_accounts().pop()
        foo_client = ApplicationClient(
            sandbox.get_algod_client(), Foo(), signer=account.signer
        )

        app_id, foo_address, _txid = foo_client.create()
        verify_app_id(app_id, AppPrecompile(Foo()), self.algod_client)

        foo_client.fund(1_000_000)

        app_id = foo_client.call(Foo.create_bar).return_value
        verify_app_id(app_id, AppPrecompile(Bar()), self.algod_client)


if __name__ == "__main__":
    unittest.main()
