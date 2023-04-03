import unittest
from typing import Final

from beaker import Application, unconditional_create_approval, sandbox
from beaker.client import ApplicationClient
from beaker.consts import algo
from beaker.lib.storage import BoxMapping
from pyteal import Expr, Seq, Assert, Not, App, Itob
from pyteal.ast import abi


class AppState:
    data: Final[BoxMapping] = BoxMapping(abi.String, abi.Uint64)


app = Application("Foo", state=AppState())
app.apply(unconditional_create_approval, initialize_global_state=True)


@app.external
def set_box_element(key: abi.String, value: abi.Uint64) -> Expr:
    return Seq(
        Assert(Not(app.state.data[key.get()].exists())),
        app.state.data[key.get()].set(value),
    )


@app.external
def set_box_element_2(key: abi.String, value: abi.Uint64) -> Expr:
    return Seq(
        length := App.box_length(key.get()),
        Assert(Not(length.hasValue())),
        App.box_put(key.get(), Itob(value.get())),
    )


class BoxMappingTestCase(unittest.TestCase):
    def test_box_mapping(self):
        account = sandbox.get_accounts().pop()
        client = ApplicationClient(
            sandbox.get_algod_client(),
            sender=account.address,
            signer=account.signer,
            app=app,
        )

        client.create()
        client.fund(1 * algo)

        client.call(
            set_box_element.method_signature(), boxes=[(0, b"foo")], key="foo", value=1
        )

    def test_box(self):
        account = sandbox.get_accounts().pop()
        client = ApplicationClient(
            sandbox.get_algod_client(),
            sender=account.address,
            signer=account.signer,
            app=app,
        )

        client.create()
        client.fund(1 * algo)

        client.call(
            set_box_element_2.method_signature(),
            boxes=[(0, b"foo")],
            key="foo",
            value=1,
        )


if __name__ == "__main__":
    unittest.main()
