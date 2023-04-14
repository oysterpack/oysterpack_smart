import unittest
from typing import Final
from unittest import IsolatedAsyncioTestCase

from algosdk.atomic_transaction_composer import TransactionWithSigner, AtomicTransactionComposer
from beaker import Application, GlobalStateValue
from beaker.client import ApplicationClient
from beaker.consts import algo
from pyteal import Expr, Seq, Assert, TealType, Global
from pyteal.ast import abi

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions import asset
from oysterpack.algorand.client.transactions.payment import transfer_algo
from tests.algorand.test_support import AlgorandTestCase


class AppState:
    asset_id: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64
    )

    asset_transfer_max_amt: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64
    )

    payment_max_amt: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64
    )


app = Application("FooActivity", state=AppState())


@app.create
def create(
        asset: abi.Asset,
        asset_transfer_max_amt: abi.Uint64,
        payment_max_amt: abi.Uint64,
) -> Expr:
    return Seq(
        app.state.asset_id.set(asset.asset_id()),
        app.state.asset_transfer_max_amt.set(asset_transfer_max_amt.get()),
        app.state.payment_max_amt.set(payment_max_amt.get()),
    )


@app.external
def execute(
        payment: abi.PaymentTransaction,
        asset_transfer: abi.AssetTransferTransaction,
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
            asset_transfer.get().asset_amount() <= app.state.asset_transfer_max_amt.get(),
            comment="asset transfer amount exceeded",
        ),
        Assert(
            asset_transfer.get().asset_close_to() == Global.zero_address(),
            comment="Closing out asset is not permitted",
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

        app_client.create(
            asset=asset_id,
            asset_transfer_max_amt=1_000_000,
            payment_max_amt=1 * algo,
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
            suggested_params=self.algod_client.suggested_params()
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
        atc.execute(self.algod_client,2)


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
            )


if __name__ == '__main__':
    unittest.main()
