from typing import Final

from algosdk.transaction import OnComplete
from beaker import (
    Application,
    ApplicationStateValue,
    Authorize,
    AppPrecompile,
    external,
)
from beaker.decorators import create, delete
from pyteal import (
    TealType,
    Expr,
    Seq,
    Int,
    Global,
    AssetHolding,
    Not,
    Reject,
    InnerTxnBuilder,
    Assert,
    InnerTxn,
    Subroutine,
    App,
    Bytes,
    TxnField,
    TxnType,
    If,
    AccountParam,
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions.assets import (
    execute_optin,
    execute_optout,
)
from oysterpack.apps.auction_app.model.auction import AuctionStatus

# TODO: can this be looked up instead of hard coded?
# one option is to manage this config in a contract's global storage
AssetMinBalance = Int(100000)


class AuctionBidEscrow(Application):
    """
    Escrow account used to hold the bid until the auction is closed.

    Notes
    -----
    - created by the Auction app account
    - all methods require authorization and can only be invoked by the creator address, i.e.,
      the Auction that created this escrow account
    """

    @external(authorize=Authorize.only(Global.creator_address()))
    def optin_asset(
        self, storage_fees: abi.PaymentTransaction, asset: abi.Asset
    ) -> Expr:
        """
        Optin the specified asset.
        If the asset is already opted in, then the call will be rejected.

        :param storage_fees: payment is required to pay for asset holding storage fees
        :param asset: asset tp opt in
        :return:
        """
        return Seq(
            # assert that the asset is not already opted in
            asset_holding := AssetHolding.balance(self.address, asset=asset.asset_id()),
            Assert(Not(asset_holding.hasValue())),
            # check payment
            Assert(
                storage_fees.get().receiver() == Global.current_application_address()
            ),
            Assert(storage_fees.get().amount() == AssetMinBalance),
            execute_optin(asset),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def close_out_asset(self, asset: abi.Asset, close_to: abi.Account) -> Expr:
        """
        Closes out the asset to the specified account.

        If the asset is not opted in, then the call will fail.

        :param asset:
        :param close_to:
        :return:
        """
        return execute_optout(asset=asset, close_to=close_to)

    @external(authorize=Authorize.only(Global.creator_address()))
    def close_out_all_assets(self, asset: abi.Asset, close_to: abi.Account) -> Expr:
        # TODO
        return Reject()

    @delete(authorize=Authorize.only(Global.creator_address()))
    def delete(self) -> Expr:
        return Seq(
            # assert that the app has opted out of all assets
            total_assets := AccountParam.totalAssets(
                Global.current_application_address()
            ),
            Assert(total_assets.value() == Int(0)),
            # close out the account back to the creator
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.receiver: Global.creator_address(),
                    TxnField.close_remainder_to: Global.creator_address(),
                    TxnField.amount: Int(0),
                }
            ),
        )


class Auction(Application):
    """
    Seller must fund the Auction contract with ALGO to pay for contract storage costs:
    - AuctionBidEscrow contract storage costs
    - asset holding storage costs
    """

    status: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(AuctionStatus.New.value),
        descr="Auction status [New, Initialized, Cancelled, Started, Sold, NotSold, Finalized]",
    )

    bid_escrow: Final[AppPrecompile] = AppPrecompile(AuctionBidEscrow())
    bid_escrow_app_id: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64
    )

    seller_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, static=True
    )

    highest_bidder_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes
    )

    min_bid: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, descr="Minimum bid price that is accepted."
    )

    start_time: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="""
        Auction start time specified as a UNIX timestamp, i.e., number of seconds since 1970-01-01. 
        The latest confirmed block UNIX timestamp is used to determine time on-chain (Global.latest_timstamp()).
        """,
    )

    end_time: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="""
        Auction end time specified as a UNIX timestamp, i.e., number of seconds since 1970-01-01. 
        The latest confirmed block UNIX timestamp is used to determine time on-chain (Global.latest_timstamp()).
        """,
    )

    @Subroutine(TealType.uint64)
    @staticmethod
    def is_seller(sender: Expr) -> Expr:
        return sender == App.globalGet(Bytes("seller_address"))

    @create
    def create(self, seller: abi.Account) -> Expr:
        return Seq(
            self.initialize_application_state(),
            self.seller_address.set(seller.address()),
        )

    @external(authorize=is_seller)
    def initialize(self) -> Expr:
        """
        Creates the AuctionBidderEscrow contract, if it has not yet been created.
        The auction can only be

        Notes
        -----
        - 0.002 ALGO transaction fees are required to cover inner transaction to create bid escrow contract
        - contract must be prefunded with at least 0.2 ALGO to pay for contract storage fees

        :return:
        """
        return If(
            self.bid_escrow_app_id.get() == Int(0),
            Seq(
                Assert(self.status.get() == Int(AuctionStatus.New.value)),
                InnerTxnBuilder.Execute(self.bid_escrow.get_create_config()),
                self.bid_escrow_app_id.set(InnerTxn.created_application_id()),
            ),
        )

    @delete(authorize=Authorize.only(Global.creator_address()))
    def delete(self, bid_escrow_app_id: abi.Application) -> Expr:
        """
        Auction can only be deleted by its creator.

        The auction can only be deleted if:
            1. status == AuctionStatus.Finalized
            2. auction has no asset holdings

        Performs the following:
            1. deletes the bid escrow contract, which closes out its ALGO balance to its Auction creator
            2. closes out the account ALGO balance to its creator

        Notes
        -----
        - There are 3 inner transactions. Fees are paid by the sender: 4000 microAlgo

        :param bid_escrow_app_id: must match the bid escrow app id, which can be looked up from global state
        :return:
        """
        return Seq(
            Assert(self.status.get() == Int(AuctionStatus.Finalized.value)),
            Assert(bid_escrow_app_id.application_id() == self.bid_escrow_app_id.get()),
            # assert that the app has opted out of all assets
            total_assets := AccountParam.totalAssets(
                Global.current_application_address()
            ),
            Assert(total_assets.value() == Int(0)),
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: self.bid_escrow_app_id.get(),
                    TxnField.on_completion: Int(OnComplete.DeleteApplicationOC.value),
                }
            ),
            # close out ALGO balance to the creator
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.receiver: Global.creator_address(),
                    TxnField.close_remainder_to: Global.creator_address(),
                    TxnField.amount: Int(0),
                }
            ),
        )
