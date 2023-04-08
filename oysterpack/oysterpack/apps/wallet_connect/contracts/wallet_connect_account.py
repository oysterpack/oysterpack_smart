"""
Wallet Connect Account
"""
from typing import Final

from beaker import Application, GlobalStateValue, Authorize
from beaker.lib.storage import BoxMapping
from pyteal import TealType, Expr, Itob, Pop, Seq, Int, Assert, Global, App, Bytes
from pyteal.ast import abi

from oysterpack.apps.wallet_connect.contracts.wallet_connect_app import WalletConnectAppState

ConnectedAppId = abi.Uint64


class WalletPublicKeys(abi.NamedTuple):
    signing_address: abi.Field[abi.Address]
    encryption_address: abi.Field[abi.Address]


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

    wallet_public_keys: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        descr="Used for messaging between the wallet and the wallet-connect-service",
    )

    apps_conns: Final[BoxMapping] = BoxMapping(ConnectedAppId, WalletPublicKeys)


application = Application("WalletConnectAccount", state=WalletConnectAccountState())


@application.create
def create(account: abi.Account) -> Expr:
    return Seq(
        application.initialize_global_state(),
        application.state.account.set(account.address()),
    )


@application.external(read_only=True)
def wallet_public_keys(app: abi.Application, *, output: WalletPublicKeys) -> Expr:
    return Seq(
        (keys := WalletPublicKeys()).decode(application.state.apps_conns[Itob(app.application_id())].get()),
        (signing_address := abi.Address()).set(keys.signing_address),
        (encryption_address := abi.Address()).set(keys.encryption_address),
        output.set(signing_address, encryption_address),
    )


@application.external(authorize=Authorize.only_creator())
def connect_app(app: abi.Application, wallet_public_keys: WalletPublicKeys) -> Expr:
    return Seq(
        # app must be created by the same creator
        app_creator:=app.params().creator_address(),
        Assert(app_creator.value() == Global.creator_address()),
        # app must be an instance of WalletConnectApp
        app_type_ulid:=App.globalGetEx(app.application_id(), WalletConnectAppState.app_type_ulid.key),
        Assert(app_type_ulid.value() == Bytes(WalletConnectAppState.APP_TYPE_ULID.bytes)),

        application.state.apps_conns[Itob(app.application_id())].set(wallet_public_keys),
    )


@application.external(authorize=Authorize.only_creator())
def disconnect_app(app_id: abi.Application) -> Expr:
    return Pop(application.state.apps_conns[Itob(app_id.application_id())].delete())


@application.external(authorize=Authorize.only_creator())
def set_wallet_public_keys(keys: WalletPublicKeys) -> Expr:
    return application.state.wallet_public_keys.set(keys.encode())
