from typing import Final

from beaker import (
    Application,
    ApplicationStateValue,
    Authorize,
    external,
)
from beaker.decorators import create, delete, internal
from pyteal import (
    TealType,
    Expr,
    Seq,
    Int,
    Global,
    AssetHolding,
    InnerTxnBuilder,
    Assert,
    Subroutine,
    App,
    Bytes,
    TxnField,
    TxnType,
    AccountParam,
    Cond,
    Approve,
    Txn,
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions.assets import (
    execute_optin,
    execute_optout,
)
from oysterpack.apps.auction_app.model.auction import AuctionStatus


class AuctionState(Application):
    status: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(AuctionStatus.New.value),
        descr="Auction status [New, Initialized, Cancelled, Started, Sold, NotSold, Finalized]",
    )

    seller_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, static=True
    )

    bid_asset_id: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, descr="Asset that is used to submit bids"
    )
    min_bid: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, descr="Minimum bid price that is accepted."
    )

    highest_bidder_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes
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

    # AuctionStatus helper functions

    def is_new(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.New.value)

    def is_committed(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.Committed.value)

    def is_started(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.Started.value)

    def is_sold(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.Sold.value)

    def is_not_sold(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.NotSold.value)

    def is_finalized(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.Finalized.value)

    def is_cancelled(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.Cancelled.value)

    # END - AuctionStatus helper functions

    @internal(TealType.uint64)
    def get_highest_bid(self) -> Expr:
        """
        Highest bid is the bid asset balance.
        """
        return AssetHolding.balance(self.address, self.bid_asset_id.get())


class AuctionAuth:
    @Subroutine(TealType.uint64)
    @staticmethod
    def is_seller(sender: Expr) -> Expr:
        """
        Used as an authorization subroutine
        """
        return sender == App.globalGet(Bytes("seller_address"))


# TODO: add standardized transaction notes
class Auction(AuctionState, AuctionAuth):
    """
    Auction is used to sell asset holdings escrowed by this contract to the highest bidder.

    Seller must fund the Auction contract with ALGO to pay for contract storage costs:
    - 0.1 ALGO for base contract storage cost
    - 0.1 ALGO for each asset holding storage costs

    When the auction is finalized, the ALGO paid for storage costs will be closed out to the creator address.
    """

    @create
    def create(self, seller: abi.Account) -> Expr:
        """
        Initializes the application global state.

        - seller address is stored in global state
        - initial status will be AuctionStatus.New

        """
        return Seq(
            self.initialize_application_state(),
            self.seller_address.set(seller.address()),
        )

    @external(authorize=AuctionAuth.is_seller)
    def set_bid_asset(self, bid_asset: abi.Asset, min_bid: abi.Uint64) -> Expr:
        """
        Opts in the bid asset, only if it has not yet been opted in.

        To change the bid asset once its set, the seller must first opt out the bid asset.

        Asserts
        -------
        1. status == AuctionStatus.New
        2. bid asset_id has not been set
        3. min bid > 0

        Inner Transactions
        ------------------
        1. opts in the asset

        Notes
        -----
        - transaction fees = 0.002 ALGO
        - contract must be prefunded to pay for contract storage costs with at least 0.2 ALGO:
          - 0.1 ALGO for contract account storage
          - 0.1 ALGO for asset holding storage
        - bid asset id and min bid are stored in global state
        """
        return Seq(
            Assert(self.is_new()),
            Assert(self.bid_asset_id.get() == Int(0)),
            Assert(min_bid.get() > Int(0)),
            self.bid_asset_id.set(bid_asset.asset_id()),
            self.min_bid.set(min_bid.get()),
            execute_optin(bid_asset),
        )

    @external(authorize=AuctionAuth.is_seller)
    def optin_asset(self, asset: abi.Asset) -> Expr:
        """
        Opt in asset to be sold in the auction.
        After the asset is opted in, then the seller can transfer the assets to the auction account.

        Notes
        -----
        - transaction fees = 0.002 ALGO
        - contract must be prefunded to pay for contract storage costs with at least 0.2 ALGO:
          - 0.1 ALGO for contract account storage
          - 0.1 ALGO for asset holding storage
        """
        return Seq(Assert(self.is_new()), execute_optin(asset))

    @external(authorize=AuctionAuth.is_seller)
    def optout_asset(self, asset: abi.Asset) -> Expr:
        return Seq(Assert(self.is_new()), execute_optout(asset, Txn.sender()))

    @external(authorize=AuctionAuth.is_seller)
    def cancel(self) -> Expr:
        """
        The auction cannot be cancelled once it has been committed.
        If the auction is already cancelled, then this is a noop.

        :return:
        """

        return Cond(
            [self.is_new(), self.status.set(Int(AuctionStatus.Cancelled.value))],
            [self.is_cancelled(), Approve()],
        )

    @delete(authorize=Authorize.only(Global.creator_address()))
    def delete(self) -> Expr:
        """
        Auction can only be deleted by its creator.

        Asserts
        -------
        1. status == AuctionStatus.Finalized
        2. auction must have no asset holdings, i.e., all asset holdings have been closed out

        Inner Transactions
        ------------------
        1. deletes the bid escrow contract
            1.1 bid escrow contract closes out its ALGO balance to its Auction creator
        2. closes out the account ALGO balance to its creator

        Notes
        -----
        - transaction fees= 0.004 ALGO

        :param bid_escrow_app_id: is required in order to delete the contract. It can be looked up from global state
        """
        return Seq(
            Assert(self.is_finalized()),
            # assert that the app has opted out of all assets
            total_assets := AccountParam.totalAssets(
                Global.current_application_address()
            ),
            Assert(total_assets.value() == Int(0)),
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
