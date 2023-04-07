"""
Wallet Connect Account
"""
from typing import Final

from beaker import Application, GlobalStateValue, Authorize
from beaker.lib.storage import BoxMapping
from pyteal import TealType, Expr, Itob, Pop, Seq, Assert, Global, Int
from pyteal.ast import abi

ConnectedAppId = abi.Uint64


class WalletPublicKeys(abi.NamedTuple):
    role: abi.Field[abi.Address]
    voted: abi.Field[abi.Address]


class WalletConnectAccountState:
    account: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        static=True,
        descr="Algorand account address",
    )

    expiration: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Wallet connect service subscription expiration, specified as a UNIX timestamp"
    )

    apps_conns: Final[BoxMapping] = BoxMapping(ConnectedAppId, WalletPublicKeys)


application = Application("WalletConnectAccount", state=WalletConnectAccountState())


@application.create
def create(account: abi.Account) -> Expr:
    return Seq(
        application.initialize_global_state(),
        application.state.account.set(account.address()),
    )

@application.external(authorize=Authorize.only_creator())
def connect_app(app: abi.Application, wallet_public_keys: WalletPublicKeys) -> Expr:
    return Seq(
        app_creator:=app.params().creator_address(),
        Assert(app_creator.value() == Global.creator_address()),
        application.state.apps_conns[Itob(app.application_id())].set(wallet_public_keys),
    )

@application.external(authorize=Authorize.only_creator())
def disconnect_app(app_id: abi.Application) -> Expr:
    return Pop(application.state.apps_conns[Itob(app_id.application_id())].delete())
