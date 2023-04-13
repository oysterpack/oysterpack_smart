"""
Wallet Connect Account
"""
from typing import Final

from algosdk.transaction import OnComplete
from beaker import Application, GlobalStateValue
from beaker.lib.storage import BoxMapping
from pyteal import (
    TealType,
    Expr,
    Itob,
    Pop,
    Seq,
    Int,
    Assert,
    Global,
    App,
    Bytes,
    Subroutine,
    If,
    Not,
    InnerTxnBuilder,
    TxnField,
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions.application import (
    execute_close_out_app,
)
from oysterpack.apps.wallet_connect.contracts import wallet_connect_app
from oysterpack.apps.wallet_connect.contracts.wallet_connect_app import (
    WalletConnectAppState,
)

ConnectedAppId = abi.Uint64


class WalletPublicKeys(abi.NamedTuple):
    signing_address: abi.Field[abi.Address]
    encryption_address: abi.Field[abi.Address]


class WalletConnectAccountState:
    account: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        static=True,
        descr="Algorand account address that owns this contract",
    )

    expiration: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Wallet connect service subscription expiration, specified as a UNIX timestamp",
    )

    wallet_public_keys: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        descr="Used for messaging between the wallet and the wallet-connect-service",
    )

    apps_conns: Final[BoxMapping] = BoxMapping(ConnectedAppId, WalletPublicKeys)


application = Application("WalletConnectAccount", state=WalletConnectAccountState())


@Subroutine(TealType.uint64)
def is_account_owner(addr: Expr) -> Expr:
    return application.state.account.get() == addr


@application.create
def create(account: abi.Account) -> Expr:
    return Seq(
        application.initialize_global_state(),
        application.state.account.set(account.address()),
    )


@application.external(authorize=is_account_owner)
def optin_app(app: abi.Application) -> Expr:
    def _optin_app() -> Expr:
        return Seq(
            # app must be created by the same creator
            app_creator := app.params().creator_address(),
            Assert(app_creator.value() == Global.creator_address()),
            # app must be an instance of WalletConnectApp
            app_type_ulid := App.globalGetEx(
                app.application_id(), WalletConnectAppState.app_type_ulid.key
            ),
            Assert(
                app_type_ulid.value() == Bytes(WalletConnectAppState.APP_TYPE.bytes)
            ),
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=app.application_id(),
                method_signature=wallet_connect_app.optin.method_signature(),
                args=[],
                extra_fields={
                    TxnField.on_completion: Int(OnComplete.OptInOC.value),
                    TxnField.fee: Int(0),
                },
            ),
        )

    return Seq(
        If(
            Not(
                App.optedIn(Global.current_application_address(), app.application_id())
            ),
            _optin_app(),
        )
    )


@application.external(authorize=is_account_owner)
def close_out_app(app: abi.Application) -> Expr:
    def _close_out_app() -> Expr:
        return Seq(
            execute_close_out_app(app.application_id()),
            Pop(application.state.apps_conns[Itob(app.application_id())].delete()),
        )

    return Seq(
        If(
            App.optedIn(Global.current_application_address(), app.application_id()),
            _close_out_app(),
        )
    )


@application.external(authorize=is_account_owner)
def connect_app(app: abi.Application, wallet_public_keys: WalletPublicKeys) -> Expr:
    return Seq(
        Assert(App.optedIn(Global.current_application_address(), app.application_id())),
        application.state.apps_conns[Itob(app.application_id())].set(
            wallet_public_keys
        ),
    )


@application.external(authorize=is_account_owner)
def disconnect_app(app: abi.Application) -> Expr:
    return Pop(application.state.apps_conns[Itob(app.application_id())].delete())


@application.external(authorize=is_account_owner)
def set_wallet_public_keys(keys: WalletPublicKeys) -> Expr:
    return application.state.wallet_public_keys.set(keys.encode())


@application.external(read_only=True)
def wallet_public_keys(app: abi.Application, *, output: WalletPublicKeys) -> Expr:
    """
    Fails if the account is not connected to the specified app

    :param app:
    :param output:
    :return:
    """
    return Seq(
        (keys := WalletPublicKeys()).decode(
            application.state.apps_conns[Itob(app.application_id())].get()
        ),
        (signing_address := abi.Address()).set(keys.signing_address),
        (encryption_address := abi.Address()).set(keys.encryption_address),
        output.set(signing_address, encryption_address),
    )
