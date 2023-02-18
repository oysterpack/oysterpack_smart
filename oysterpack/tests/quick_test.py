import unittest
from time import sleep
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
    def test_indexer_paging_apps(self):
        account = sandbox.get_accounts().pop()
        foo_client = ApplicationClient(
            sandbox.get_algod_client(), Foo(), signer=account.signer
        )

        _app_id, foo_address, _txid = foo_client.create()
        foo_client.fund(1_000_000)

        def next_page(result) -> str:
            next_token = result.setdefault("next-token", None)
            print("next_token =", next_token)
            return next_token

        def app_ids(result) -> list[int]:
            apps = result["applications"]
            return [app["id"] for app in apps]

        # create 3 apps
        app_ids_created = []
        for _ in range(5):
            app_ids_created.append(
                foo_client.call(Foo.create_bar, owner=foo_address).return_value
            )

        sleep(1)  # give time for indexing

        indexer_client = sandbox.get_indexer_client()
        result = indexer_client.search_applications(creator=foo_address, limit=2)
        app_ids_returned = app_ids(result)
        self.assertEqual(len(app_ids_returned), 2)

        print("app_ids_created =", app_ids_created)
        print("app_ids_returned =", app_ids_returned)
        print("*" * 10)

        # create another Foo app instance between paging
        app_ids_created.append(
            foo_client.call(Foo.create_bar, owner=foo_address).return_value
        )
        sleep(1)  # give time for indexingsleep(1)

        # continue paging
        result = indexer_client.search_applications(
            creator=foo_address,
            limit=2,
            next_page=next_page(result),
        )
        app_ids_returned += app_ids(result)
        self.assertEqual(len(app_ids_returned), 4)
        print("app_ids_created =", app_ids_created)
        print("app_ids_returned =", app_ids_returned)
        print("*" * 10)

        result = indexer_client.search_applications(
            creator=foo_address,
            limit=2,
            next_page=next_page(result),
        )
        app_ids_returned += app_ids(result)
        self.assertEqual(len(app_ids_returned), 6)
        print("app_ids_created =", app_ids_created)
        print("app_ids_returned =", app_ids_returned)
        print("*" * 10)

        # create another Foo app instance after all search results have been retrieved
        app_ids_created.append(
            foo_client.call(Foo.create_bar, owner=foo_address).return_value
        )
        sleep(1)  # give time for indexingsleep(1)

        result = indexer_client.search_applications(
            creator=foo_address,
            limit=2,
            next_page=next_page(result),
        )
        app_ids_returned += app_ids(result)
        self.assertEqual(len(app_ids_returned), 7)
        print("app_ids_created =", app_ids_created)
        print("app_ids_returned =", app_ids_returned)
        print("*" * 10)


if __name__ == "__main__":
    unittest.main()
