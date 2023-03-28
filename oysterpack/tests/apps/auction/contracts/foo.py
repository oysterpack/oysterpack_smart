from beaker import Application, Authorize
from pyteal import Expr, Approve, Seq, Log
from pyteal.ast import abi

app = Application("foo")


@app.create
def create(seller: abi.Account) -> Expr:  # pylint: disable=arguments-differ
    return Seq(Log(seller.address()), Approve())


@app.delete(authorize=Authorize.only_creator())
def delete() -> Expr:
    return Approve()
