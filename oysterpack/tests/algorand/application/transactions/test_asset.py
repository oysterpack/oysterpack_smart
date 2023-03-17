import unittest
from typing import cast, Any

from algosdk.transaction import wait_for_confirmation
from beaker import Application, Authorize
from beaker.client import ApplicationClient
from pyteal import (
    Expr,
    Global,
    InnerTxnBuilder,
    Int,
    If,
    AssetHolding,
    Seq,
    Assert,
    AccountParam,
    ABIReturnSubroutine,
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions import payment
from oysterpack.algorand.application.transactions.asset import (
    execute_optin,
    execute_transfer,
    execute_optout,
    set_optin_txn_fields,
    set_optout_txn_fields,
    set_transfer_txn_fields,
)
from oysterpack.algorand.client.accounts import get_auth_address_callable
from oysterpack.algorand.client.accounts.kmd import (
    WalletSession,
    WalletTransactionSigner,
)
from oysterpack.algorand.client.transactions import asset as client_assets
from tests.algorand.test_support import AlgorandTestCase

app = Application("foo")


@app.external(authorize=Authorize.only(Global.creator_address()))
def execute_optin_asset(asset: abi.Asset) -> Expr:
    return execute_optin(asset)


@app.external(authorize=Authorize.only(Global.creator_address()))
def execute_optout_asset(asset: abi.Asset) -> Expr:
    return Seq(
        maybe_value := AssetHolding.balance(
            Global.current_application_address(), asset.asset_id()
        ),
        If(maybe_value.hasValue(), execute_optout(asset)),
    )


@app.external
def execute_asset_transfer(receiver: abi.Account, asset: abi.Asset, amount: abi.Uint64):
    return execute_transfer(receiver, asset, amount)


@app.external(authorize=Authorize.only(Global.creator_address()))
def submit_optin_asset(asset: abi.Asset) -> Expr:
    return Seq(
        InnerTxnBuilder.Begin(),
        set_optin_txn_fields(asset),
        InnerTxnBuilder.Submit(),
    )


@app.external(authorize=Authorize.only(Global.creator_address()))
def submit_optout_asset(asset: abi.Asset) -> Expr:
    return Seq(
        maybe_value := AssetHolding.balance(
            Global.current_application_address(), asset.asset_id()
        ),
        If(
            maybe_value.hasValue(),
            Seq(
                InnerTxnBuilder.Begin(),
                set_optout_txn_fields(asset),
                InnerTxnBuilder.Submit(),
            ),
        ),
    )


@app.external
def submit_asset_transfer(
    receiver: abi.Account,
    asset: abi.Asset,
    amount: abi.Uint64,
):
    return Seq(
        InnerTxnBuilder.Begin(),
        set_transfer_txn_fields(receiver=receiver, asset=asset, amount=amount),
        InnerTxnBuilder.Submit(),
    )


@app.delete(authorize=Authorize.only(Global.creator_address()))
def delete() -> Expr:
    return Seq(
        # assert that the app has opted out of all assets
        total_assets := AccountParam.totalAssets(Global.current_application_address()),
        Assert(total_assets.value() == Int(0)),
        # close out the account back to the creator
        InnerTxnBuilder.Execute(payment.close_out(Global.creator_address())),
    )


class AssetOptInOptOutTestCase(AlgorandTestCase):
    def optin_optout_test_template(
        self,
        optin: ABIReturnSubroutine,
        optout: ABIReturnSubroutine,
        transfer: ABIReturnSubroutine,
    ):
        """
        Test template
        1. create asset
        2. create app
        3. fund app
        4. opt app into asset
        5. transfer assets to app
        6. opt app out of asset
        7. delete app
        :return:
        """

        # create asset
        asset_id, asset_manager = self.create_test_asset(asset_name="GOLD")

        app_client = ApplicationClient(
            client=self.algod_client,
            app=app,
            sender=asset_manager.account,
            signer=WalletTransactionSigner(
                WalletSession.from_wallet(
                    asset_manager.wallet, get_auth_address_callable(self.algod_client)
                )
            ),
        )

        print(f"app_client.sender = {app_client.sender}")

        account_info = cast(
            dict[str, Any], self.algod_client.account_info(cast(str, app_client.sender))
        )
        account_starting_balance = account_info["amount"]

        # create app
        app_client.create(sender=asset_manager.account)

        # opt app into asset

        # fund tha app
        # 0.1 ALGO for global state
        # 0.1 ALGO for asset holding
        app_client.fund(100_000 * 2)

        # transaction must pay for opt-in inner transaction
        sp = self.algod_client.suggested_params()
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True
        app_client.call(
            optin, asset=asset_id, suggested_params=sp, sender=asset_manager.account
        )

        # assert that the app holds the asset
        app_account_info = app_client.get_application_account_info()
        self.assertTrue(
            [
                app_asset
                for app_asset in app_account_info["assets"]
                if app_asset["asset-id"] == asset_id
            ]
        )

        # transfer assets to app
        txn = client_assets.transfer(
            sender=asset_manager.account,
            receiver=app_client.get_application_account_info()["address"],
            asset_id=asset_id,
            suggested_params=app_client.client.suggested_params(),
            amount=10000,
        )
        signed_txn = asset_manager.wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # transfer assets back to manager account
        print(f"asset_id={asset_id} asset_manager_address={asset_manager.account}")
        app_client.call(
            transfer,
            receiver=asset_manager.account,
            asset=asset_id,
            amount=2000,
            suggested_params=sp,
            sender=asset_manager.account,
        )

        # assert that the assets were transferred
        app_account_info = app_client.get_application_account_info()
        self.assertEqual(app_account_info["assets"][0]["amount"], 8000)
        account_asset_info = cast(
            dict[str, Any],
            app_client.client.account_asset_info(asset_manager.account, asset_id),
        )
        self.assertEqual(
            account_asset_info["asset-holding"]["amount"], 1_000_000_000_000_000 - 8000
        )

        app_client.call(
            optout,
            asset=asset_id,
            suggested_params=sp,
            sender=asset_manager.account,
        )

        app_account_info = app_client.get_application_account_info()
        self.assertEqual(app_account_info["total-assets-opted-in"], 0)

        app_client.delete(suggested_params=sp, sender=asset_manager.account)
        account_info = cast(
            dict[str, Any], self.algod_client.account_info(cast(str, app_client.sender))
        )
        account_ending_balance = account_info["amount"]

        if account_starting_balance > account_ending_balance:
            # when the app is deleted, the app account should have been closed out to the app creator
            # the account ending balance should be the starting balance minus transaction fees
            total_txn_fees = 1000  # create
            total_txn_fees += 1000  # fund
            total_txn_fees += 2000  # optin
            total_txn_fees += 1000  # asset transfer to app
            total_txn_fees += 2000  # app transferred assets
            total_txn_fees += 2000  # optout
            total_txn_fees += 2000  # delete
            self.assertEqual(
                total_txn_fees, account_starting_balance - account_ending_balance
            )
        else:  # account received ALGO rewards, which resulted in ending balance > starting balance
            pass

    def test_execute_optin_optout(self):
        self.optin_optout_test_template(
            execute_optin_asset,
            execute_optout_asset,
            execute_asset_transfer,
        )

    def test_submit_optin_optout(self):
        self.optin_optout_test_template(
            submit_optin_asset,
            submit_optout_asset,
            submit_asset_transfer,
        )


if __name__ == "__main__":
    unittest.main()
