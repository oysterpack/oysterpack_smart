from typing import Final

from beaker import (
    Application,
    ApplicationStateValue,
    Authorize,
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
    If,
    Or,
    Not,
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions.assets import (
    execute_optin,
    execute_optout,
    execute_transfer,
)
from oysterpack.apps.auction_app.model.auction import AuctionStatus


class _AuctionState(Application):
    status: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(AuctionStatus.New.value),
        descr="Auction status [New, Initialized, Cancelled, Started, Sold, NotSold, Finalized]",
    )

    seller_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, static=True
    )

    bid_asset_id: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="Asset that is used to submit bids",
    )
    min_bid: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="Minimum bid price that is accepted.",
    )

    highest_bidder_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes
    )

    highest_bid: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
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

    def is_bid_accepted(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.BidAccepted.value)

    def is_finalized(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.Finalized.value)

    def is_cancelled(self) -> Expr:
        return self.status.get() == Int(AuctionStatus.Cancelled.value)

    # END - AuctionStatus helper functions


class _AuctionAuth:
    @Subroutine(TealType.uint64)
    @staticmethod
    def is_seller(sender: Expr) -> Expr:
        """
        Used as an authorization subroutine
        """
        return sender == App.globalGet(Bytes("seller_address"))


# TODO: add standardized transaction notes
class Auction(_AuctionState, _AuctionAuth):
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

    @external(authorize=_AuctionAuth.is_seller)
    def set_bid_asset(self, bid_asset: abi.Asset, min_bid: abi.Uint64) -> Expr:
        """
        Opts in the bid asset, only if it has not yet been opted in.

        To change the bid asset once its set, the seller must first opt out the bid asset.
        The min bid can be updated if the bid_asset is not being changed.

        Asserts
        -------
        1. status == AuctionStatus.New
        2. bid asset_id == 0 or is the same
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
            Assert(
                self.is_new(),
                min_bid.get() > Int(0),
                Or(
                    self.bid_asset_id.get() == Int(0),
                    self.bid_asset_id.get() == bid_asset.asset_id(),
                ),
            ),
            self.bid_asset_id.set(bid_asset.asset_id()),
            self.min_bid.set(min_bid.get()),
            # if the auction does not hold the bid asset, then opt in the bid asset
            bid_asset_holding := AssetHolding.balance(
                self.address, bid_asset.asset_id()
            ),
            If(
                Not(bid_asset_holding.hasValue()),
                execute_optin(bid_asset),
            ),
        )

    @external(authorize=_AuctionAuth.is_seller)
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
        return Seq(
            Assert(self.is_new()),
            execute_optin(asset),
        )

    @external(authorize=_AuctionAuth.is_seller)
    def optout_asset(self, asset: abi.Asset) -> Expr:
        """
        Closes out the asset to the seller

        Asserts
        -------
        1. auction status is `New`
        """

        return Seq(
            Assert(self.is_new()),
            execute_optout(asset, Txn.sender()),
            # If the bid asset is being opted out, then reset `bid_set_id` to zero
            # NOTE: in order to change the bid asset, it must first be opted out.
            If(
                asset.asset_id() == self.bid_asset_id.get(),
                self.bid_asset_id.set(Int(0)),
            ),
        )

    @external(authorize=_AuctionAuth.is_seller)
    def withdraw_asset(self, asset: abi.Asset, amount: abi.Uint64) -> Expr:
        """
        Assets can only be withdrawn when auction status is `New`

        Notes
        -----
        - transaction fees = 0.002 ALGO

        :param asset:
        :param amount:
        :return:
        """
        return Seq(
            Assert(self.is_new()),
            execute_transfer(Txn.sender(), asset, amount),
        )

    @external(authorize=_AuctionAuth.is_seller)
    def commit(self, start_time: abi.Uint64, end_time: abi.Uint64) -> Expr:
        return Seq(
            Assert(
                self.is_new(),
                self.bid_asset_id.get() != Int(0),
                self.min_bid.get() > Int(0),
            ),
            # besides the bid asset, there should be at least 1 asset for sale
            #
            # NOTE:
            # - asset balances should be > 0, but are not checked here
            # - client should check the asset balances before committing
            total_assets := AccountParam.totalAssets(self.address),
            Assert(
                total_assets.value() > Int(1),
                start_time.get() >= Global.latest_timestamp(),
                end_time.get() > start_time.get(),
            ),
            self.start_time.set(start_time.get()),
            self.end_time.set(end_time.get()),
            self.status.set(Int(AuctionStatus.Committed.value)),
        )

    @external(authorize=_AuctionAuth.is_seller)
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

    @external
    def bid(
        self,
        bid: abi.AssetTransferTransaction,
        highest_bidder: abi.Account,
    ) -> Expr:
        """

        Asserts
        -------
        1. auction status == Committed
        2. bid asset
        3. bid asset transfer received is this contract

        Notes
        -----
        - new highest bidder is set to the bid sender

        """
        return Seq(
            Assert(
                self.status.get() == Int(AuctionStatus.Committed.value),
                # check auction bidding has started
                Global.latest_timestamp() >= self.start_time.get(),
                Global.latest_timestamp() <= self.end_time.get(),
                bid.get().asset_receiver() == self.address,
                bid.get().xfer_asset() == self.bid_asset_id.get(),
                bid.get().asset_amount() > self.highest_bid.get(),
            ),
            # refund the current highest bidder
            # if this is the first bid (highes_bid == 0), then no refund is needed
            If(
                self.highest_bid.get() > Int(0),
                Seq(
                    Assert(
                        highest_bidder.address() == self.highest_bidder_address.get()
                    ),
                    # TODO: add transaction note
                    execute_transfer(
                        receiver=highest_bidder,
                        asset=self.bid_asset_id.get(),
                        amount=self.highest_bid.get(),
                    ),
                ),
            ),
            self.highest_bidder_address.set(bid.get().sender()),
            self.highest_bid.set(bid.get().asset_amount()),
        )

    @external(read_only=True)
    def latest_timestamp(self, *, output: abi.Uint64) -> Expr:
        """
        Get the latest confirmed block UNIX timestamp
        """
        return output.set(Global.latest_timestamp())
