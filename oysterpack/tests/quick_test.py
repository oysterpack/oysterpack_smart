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

    def test_sqlite_fts5(self):
        import sqlite3

        con = sqlite3.connect(":memory:")
        cur = con.cursor()
        cur.execute(
            "CREATE VIRTUAL TABLE if not exists email USING fts5(sender, title, body)"
        )
        res = cur.execute("SELECT name FROM sqlite_master")
        for row in res:
            print(row)
        con.commit()

    def test_delete_dict_entries_while_iterating(self):
        data = {1: 1, 2: 2}
        items = list(data.items())
        for k, v in items:
            del data[k]
        print(data)
        self.assertEqual(0, len(data))


if __name__ == "__main__":
    unittest.main()
