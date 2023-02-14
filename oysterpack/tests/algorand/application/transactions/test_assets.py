import unittest
from pprint import pp
from typing import Callable

from algosdk.transaction import wait_for_confirmation
from beaker import Application, Authorize
from beaker import sandbox
from beaker.decorators import external, delete
from beaker.sandbox import kmd
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
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions import payments
from oysterpack.algorand.application.transactions.assets import (
    execute_optin,
    execute_transfer,
    execute_optout,
    set_optin_txn_fields,
    set_optout_txn_fields,
    set_transfer_txn_fields,
)
from oysterpack.algorand.client.model import AssetId, Address
from oysterpack.algorand.client.transactions import assets as client_assets
from tests.algorand.test_support import AlgorandTestSupport


class Foo(Application):
    @external(authorize=Authorize.only(Global.creator_address()))
    def execute_optin_asset(self, asset: abi.Asset) -> Expr:
        return execute_optin(asset)

    @external(authorize=Authorize.only(Global.creator_address()))
    def execute_optout_asset(self, asset: abi.Asset) -> Expr:
        return Seq(
            maybe_value := AssetHolding.balance(
                Global.current_application_address(), asset.asset_id()
            ),
            If(maybe_value.hasValue(), execute_optout(asset)),
        )

    @external
    def execute_asset_transfer(
            self, receiver: abi.Account, asset: abi.Asset, amount: abi.Uint64
    ):
        return execute_transfer(receiver, asset, amount)

    @external(authorize=Authorize.only(Global.creator_address()))
    def submit_optin_asset(self, asset: abi.Asset) -> Expr:
        return Seq(
            InnerTxnBuilder.Begin(),
            set_optin_txn_fields(asset),
            InnerTxnBuilder.Submit(),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def submit_optout_asset(self, asset: abi.Asset) -> Expr:
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

    @external
    def submit_asset_transfer(
            self,
            receiver: abi.Account,
            asset: abi.Asset,
            amount: abi.Uint64,
    ):
        return Seq(
            InnerTxnBuilder.Begin(),
            set_transfer_txn_fields(receiver=receiver, asset=asset, amount=amount),
            InnerTxnBuilder.Submit(),
        )

    @delete(authorize=Authorize.only(Global.creator_address()))
    def delete(self) -> Expr:
        return Seq(
            # assert that the app has opted out of all assets
            total_assets := AccountParam.totalAssets(
                Global.current_application_address()
            ),
            Assert(total_assets.value() == Int(0)),
            # close out the account back to the creator
            InnerTxnBuilder.Execute(payments.close_out(Global.creator_address())),
        )


def create_test_asset() -> tuple[AssetId, Address]:
    """
    Creates a new asset using the first account in the sandbox default wallet as the administrative accounts.

    Returns (AssetId, manager account address)
    """

    def metadata_hash() -> bytes:
        import hashlib

        m = hashlib.sha256()
        m.update(b"asset metadata")
        return m.digest()

    sandbox.get_accounts().pop()
    sender = Address(sandbox.get_accounts().pop().address)
    manager = reserve = freeze = clawback = sender
    total_base_units = 1_000_000_000_000_000
    decimals = 6
    asset_name = "GOLD"
    unit_name = "GLD"
    url = "https://meld.gold/"
    txn = client_assets.create(
        sender=sender,
        manager=manager,
        reserve=reserve,
        freeze=freeze,
        clawback=clawback,
        asset_name=asset_name,
        unit_name=unit_name,
        url=url,
        metadata_hash=metadata_hash(),
        total_base_units=total_base_units,
        decimals=decimals,
        suggested_params=sandbox.get_algod_client().suggested_params(),
    )
    signed_txn = kmd.get_sandbox_default_wallet().sign_transaction(txn)
    txid = sandbox.get_algod_client().send_transaction(signed_txn)
    tx_info = wait_for_confirmation(
        algod_client=sandbox.get_algod_client(), txid=txid, wait_rounds=4
    )

    asset_id, address = (AssetId(tx_info["asset-index"]), Address(manager))
    pp(sandbox.get_algod_client().account_asset_info(address, asset_id))
    return asset_id, address


class AssetOptInOptOutTestCase(AlgorandTestSupport, unittest.TestCase):
    def optin_optout_test_template(
            self,
            optin: Callable[..., Expr],
            optout: Callable[..., Expr],
            transfer: Callable[..., Expr],
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

        app_client = self.sandbox_application_client(Foo())
        # create asset
        asset_id, asset_manager_address = create_test_asset()

        account_starting_balance = self.algod_client.account_info(app_client.sender)[
            "amount"
        ]

        # create app
        app_client.create()

        def log(event: str):
            app_account_info = app_client.get_application_account_info()
            account_balance = self.algod_client.account_info(app_client.sender)[
                "amount"
            ]
            pp(
                {
                    "event": event,
                    "account_starting_balance": account_starting_balance,
                    "account_balance": account_balance,
                    "balance_diff": account_starting_balance - account_balance,
                    "app": {
                        "balance": app_account_info["amount"],
                        "min-balance": app_account_info["min-balance"],
                        "total-assets-opted-in": app_account_info[
                            "total-assets-opted-in"
                        ],
                        "assets": app_account_info["assets"],
                    },
                }
            )

        log("created app")

        # opt app into asset

        # fund tha app
        # 0.1 ALGO for global state
        # 0.1 ALGO for asset holding
        app_client.fund(100_000 * 2)
        log("funded app")

        # transaction must pay for opt-in inner transaction
        sp = self.algod_client.suggested_params()
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True
        app_client.call(optin, asset=asset_id, suggested_params=sp)
        log("app opted-in asset")
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
            sender=Address(asset_manager_address),
            receiver=app_client.get_application_account_info()["address"],
            asset_id=asset_id,
            suggested_params=app_client.client.suggested_params(),
            amount=10000,
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)
        log("transferred assets to app")

        # transfer assets back to manager account
        print(f"asset_id={asset_id} asset_manager_address={asset_manager_address}")
        app_client.call(
            transfer,
            receiver=asset_manager_address,
            asset=asset_id,
            amount=2000,
            suggested_params=sp,
        )
        log("app transfered assets")
        # assert that the assets were transferred
        app_account_info = app_client.get_application_account_info()
        self.assertEqual(app_account_info["assets"][0]["amount"], 8000)
        account_asset_info = app_client.client.account_asset_info(
            asset_manager_address, asset_id
        )
        self.assertEqual(
            account_asset_info["asset-holding"]["amount"], 1_000_000_000_000_000 - 8000
        )

        app_client.call(optout, asset=asset_id, suggested_params=sp)
        log("app opted-out asset")
        app_account_info = app_client.get_application_account_info()
        self.assertEqual(app_account_info["total-assets-opted-in"], 0)

        app_client.delete(suggested_params=sp)
        account_ending_balance = self.algod_client.account_info(app_client.sender)[
            "amount"
        ]
        pp(
            {
                "event": "deleted app",
                "account_starting_balance": account_starting_balance,
                "account_balance": account_ending_balance,
                "balance_diff": account_starting_balance - account_ending_balance,
            }
        )

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
            Foo.execute_optin_asset,
            Foo.execute_optout_asset,
            Foo.execute_asset_transfer,
        )

    def test_submit_optin_optout(self):
        self.optin_optout_test_template(
            Foo.submit_optin_asset,
            Foo.submit_optout_asset,
            Foo.submit_asset_transfer,
        )


if __name__ == "__main__":
    unittest.main()
