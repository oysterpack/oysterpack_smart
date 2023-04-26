import unittest
from typing import Final
from unittest import IsolatedAsyncioTestCase

from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
    AtomicTransactionComposer,
)
from beaker import Application, GlobalStateValue, unconditional_create_approval
from beaker.client import ApplicationClient
from beaker.consts import algo
from pyteal import Expr, Seq, Assert, TealType, Global, Int, Bytes
from pyteal.ast import abi

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions import asset
from oysterpack.algorand.client.transactions.payment import transfer_algo
from tests.algorand.test_support import AlgorandTestCase

bar = Application("Bar")
bar.apply(unconditional_create_approval)


@bar.external
def add(x: abi.Uint64, y: abi.Uint64, *, output: abi.Uint64) -> Expr:
    return output.set(x.get() + y.get())


class AppState:
    asset_id: Final[GlobalStateValue] = GlobalStateValue(stack_type=TealType.uint64)

    asset_transfer_max_amt: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64
    )

    payment_max_amt: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64
    )

    bar_app_id: Final[GlobalStateValue] = GlobalStateValue(stack_type=TealType.uint64)


app = Application("FooActivity", state=AppState())


@app.create
def create(
        asset: abi.Asset,
        asset_transfer_max_amt: abi.Uint64,
        payment_max_amt: abi.Uint64,
        bar_app: abi.Application,
) -> Expr:
    return Seq(
        app.state.asset_id.set(asset.asset_id()),
        app.state.asset_transfer_max_amt.set(asset_transfer_max_amt.get()),
        app.state.payment_max_amt.set(payment_max_amt.get()),
        app.state.bar_app_id.set(bar_app.application_id()),
    )


@app.external
def execute(
        payment: abi.PaymentTransaction,
        asset_transfer: abi.AssetTransferTransaction,
        bar_add: abi.ApplicationCallTransaction,
) -> Expr:
    return Seq(
        Assert(
            payment.get().amount() <= app.state.payment_max_amt.get(),
            comment="ALGO transfer amount exceeded",
        ),
        Assert(
            payment.get().rekey_to() == Global.zero_address(),
            comment="Rekeying is not permitted",
        ),
        Assert(
            payment.get().close_remainder_to() == Global.zero_address(),
            comment="Closing out Algorand account is not permitted",
        ),
        Assert(
            asset_transfer.get().xfer_asset() == app.state.asset_id.get(),
            comment="invalid asset ID",
        ),
        Assert(
            asset_transfer.get().asset_amount()
            <= app.state.asset_transfer_max_amt.get(),
            comment="asset transfer amount exceeded",
        ),
        Assert(
            asset_transfer.get().asset_close_to() == Global.zero_address(),
            comment="Closing out asset is not permitted",
        ),
        Assert(
            bar_add.get().application_args.length() == Int(3),
            comment="Expected 3 args: method_name, x, y",
        ),
        Assert(
            bar_add.get().application_id() == app.state.bar_app_id.get(),
            comment="Invalid bar app ID",
        ),
        Assert(
            bar_add.get().application_args[0] == Bytes(add.method_spec().get_selector()),
            comment="Invalid bar method selector",
        ),
    )


class MyTestCase(AlgorandTestCase, IsolatedAsyncioTestCase):
    def test_validate(self):
        asset_id, wallet_account = self.create_test_asset("GOLD$")
        app_client = ApplicationClient(
            self.algod_client,
            app=app,
            sender=wallet_account.account,
            signer=wallet_account.transaction_signer(self.algod_client),
        )

        bar_client = ApplicationClient(
            self.algod_client,
            app=bar,
            sender=wallet_account.account,
            signer=wallet_account.transaction_signer(self.algod_client),
        )
        bar_app_id, _bar_app_addr, _txid = bar_client.create()

        app_client.create(
            asset=asset_id,
            asset_transfer_max_amt=1_000_000,
            payment_max_amt=1 * algo,
            bar_app=bar_app_id,
        )

        receiver = AlgoPrivateKey()
        payment = transfer_algo(
            sender=wallet_account.account,
            receiver=receiver.signing_address,
            amount=MicroAlgos(300_000),
            suggested_params=self.algod_client.suggested_params(),
        )
        optin_asset = asset.opt_in(
            account=receiver.signing_address,
            asset_id=asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                payment,
                wallet_account.transaction_signer(self.algod_client),
            ),
        )
        atc.add_transaction(
            TransactionWithSigner(
                optin_asset,
                receiver,
            ),
        )
        atc.execute(self.algod_client, 2)

        with self.subTest("valid transactions"):
            payment = transfer_algo(
                sender=wallet_account.account,
                receiver=receiver.signing_address,
                amount=MicroAlgos(100_000),
                suggested_params=self.algod_client.suggested_params(),
            )
            asset_transfer = asset.transfer(
                sender=wallet_account.account,
                receiver=receiver.signing_address,
                asset_id=asset_id,
                amount=MicroAlgos(100_000),
                suggested_params=self.algod_client.suggested_params(),
            )

            atc = AtomicTransactionComposer()
            bar_client.add_method_call(
                atc=atc,
                method=add,
                x=1,
                y=2,
            )

            app_client.call(
                execute.method_signature(),
                payment=TransactionWithSigner(
                    payment,
                    wallet_account.transaction_signer(self.algod_client),
                ),
                asset_transfer=TransactionWithSigner(
                    asset_transfer,
                    wallet_account.transaction_signer(self.algod_client),
                ),
                bar_add=atc.txn_list[0],
            )


if __name__ == "__main__":
    unittest.main()
