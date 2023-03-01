"""
Auction smart contract
"""

from typing import Final, Any

from beaker.application import Application
from beaker.consts import algo
from beaker.decorators import create, delete, external, Authorize
from beaker.state import ApplicationStateValue
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
    AccountParam,
    Cond,
    Approve,
    Txn,
    If,
    Or,
    Not,
    And,
    Reject,
)
from pyteal.ast import abi

from oysterpack.algorand.application.transactions import payment
from oysterpack.algorand.application.transactions.asset import (
    execute_optin,
    execute_optout,
    execute_transfer,
)
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus


class _AuctionState:
    # pylint: disable=invalid-name

    status: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(AuctionStatus.NEW.value),
    )

    seller_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        static=True,
    )

    bid_asset_id: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="Asset that is used to submit bids, i.e., the asset that the seller is accepting as payment",
    )
    min_bid: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="Minimum bid price that the seller will accept.",
    )

    highest_bidder_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes
    )
    highest_bid: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )

    # NOTE: The latest confirmed block UNIX timestamp is used on-chain (Global.latest_timstamp()).
    start_time: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="Auction start time specified as a UNIX timestamp.",
    )
    end_time: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="Auction end time specified as a UNIX timestamp.",
    )

    def is_new(self) -> Expr:
        """
        :return: True if status is New
        """
        return self.status.get() == Int(AuctionStatus.NEW.value)

    def is_committed(self) -> Expr:
        """
        :return: True if status is Committed
        """
        return self.status.get() == Int(AuctionStatus.COMMITTED.value)

    def is_bid_accepted(self) -> Expr:
        """
        :return: True if status is BidAccepted
        """
        return self.status.get() == Int(AuctionStatus.BID_ACCEPTED.value)

    def is_cancelled(self) -> Expr:
        """
        :return: True if status is Cancelled
        """
        return self.status.get() == Int(AuctionStatus.CANCELLED.value)

    def is_finalized(self) -> Expr:
        """
        :return: True if status is Finalized
        """
        return self.status.get() == Int(AuctionStatus.FINALIZED.value)


class Auction(Application, _AuctionState):
    """
    Auction is used to sell asset holdings escrowed by this contract to the highest bidder.

    Seller must fund the Auction contract with ALGO to pay for contract storage costs:
    - 0.1 ALGO for base contract storage cost
    - 0.1 ALGO for each asset holding storage costs

    When the auction is finalized, the ALGO paid for storage costs will be closed out to the creator address.
    """

    APP_NAME: Final[str] = "oysterpack.Auction"

    @Subroutine(TealType.uint64)
    @staticmethod
    def is_seller(sender: Expr) -> Expr:
        """
        Used as an authorization subroutine
        """
        return sender == App.globalGet(Bytes("seller_address"))

    @create
    def create(self, seller: abi.Account) -> Expr:  # pylint: disable=arguments-differ
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
            InnerTxnBuilder.Execute(payment.close_out(Global.creator_address())),
        )

    @external(read_only=True)
    def app_name(self, *, output: abi.String) -> Expr:
        """
        Returns the application name
        """
        return output.set(self.APP_NAME)

    @external(authorize=is_seller)
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
        4. asset cannot be frozen or clawed back

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
            self._assert_no_freeze_clawback(bid_asset),
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

    @external(authorize=is_seller)
    def optin_asset(self, asset: abi.Asset) -> Expr:
        """
        Opt in asset to be sold in the auction.
        After the asset is opted in, then the seller can transfer the assets to the auction account.

        Asserts
        -------
        1. asset cannot be frozen or clawed back

        Notes
        -----
        - transaction fees = 0.002 ALGO
        - contract must be prefunded to pay for contract storage costs with at least 0.2 ALGO:
          - 0.1 ALGO for contract account storage (1 time cost)
          - 0.1 ALGO for asset holding storage (for each asset holding)
        """
        return Seq(
            Assert(self.is_new()),
            self._assert_no_freeze_clawback(asset),
            execute_optin(asset),
        )

    @external(authorize=is_seller)
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

    @external(authorize=is_seller)
    def withdraw_asset(self, asset: abi.Asset, amount: abi.Uint64) -> Expr:
        """
        Assets can only be withdrawn when auction status is `New`

        Notes
        -----
        - transaction fees = 0.002 ALGO
        """
        return Seq(
            Assert(self.is_new()),
            execute_transfer(Txn.sender(), asset, amount),
        )

    @external(authorize=is_seller)
    def commit(self, start_time: abi.Uint64, end_time: abi.Uint64) -> Expr:
        """
        When the seller is done setting up the auction, the final step is to commit the auction.
        Once the auction is committed, it can no longer be changed.

        :param start_time: when the bidding session starts
        :param end_time: when the bidding session ends
        """
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
            self.status.set(Int(AuctionStatus.COMMITTED.value)),
        )

    @external(authorize=is_seller)
    def cancel(self) -> Expr:
        """
        The auction cannot be cancelled once it has been committed.

        - If the auction is already cancelled, then this is a noop.

        :return:
        """

        handle_is_new = Seq(
            total_assets := AccountParam.totalAssets(self.address),
            If(
                total_assets.value() == Int(0),  # all assets have been closed out
                self.status.set(Int(AuctionStatus.FINALIZED.value)),
                self.status.set(Int(AuctionStatus.CANCELLED.value)),
            ),
        )

        return Cond(
            [self.is_new(), handle_is_new],
            [self.is_cancelled(), Approve()],
        )

    @external
    def bid(
        self,
        bid: abi.AssetTransferTransaction,
        highest_bidder: abi.Account,
        bid_asset: abi.Asset,
    ) -> Expr:
        """
        Used to submit a bid.

        - The bid transaction sender is used as the bidder account, i.e., not the auction smart contract call transaction sender.
        - If the bid becomes the new highest bid, then the previous bidder is automatically refunded.
          - If the previous bidder has opted out of the bid asset, then the bid assets are retained by the auction contract

        Asserts
        -------
        1. auction status == Committed
        2. bid asset transfer
        3. bid asset transfer receiver is this auction contract
        4. bid > current highest bid
        4. auction bidding is open, i.e., Global.latest_timestamp() is within the start and end time window
        5. If the auction already had a bid, then the current highest bidder's account must be passed in
           - this is needed to refund the previous bidder

        Inner Transactions
        ------------------
        1. If this bid is replacing the previous bid, i.e., this is not the first bid, then an asset transfer transaction
           is issued to refund the previous highest bidder's account.

        :param bid: bid payment
        :param highest_bidder: required to be able to refund previous highest bidder
        :param bid_asset: required to be able to refund previous highest bidder
        """
        return Seq(
            Assert(
                self.status.get() == Int(AuctionStatus.COMMITTED.value),
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
                        highest_bidder.address() == self.highest_bidder_address.get(),
                        bid_asset.asset_id() == self.bid_asset_id.get(),
                    ),
                    bid_asset_holding := AssetHolding.balance(
                        highest_bidder.address(), bid_asset.asset_id()
                    ),
                    If(
                        bid_asset_holding.hasValue(),
                        execute_transfer(
                            receiver=highest_bidder,
                            asset=self.bid_asset_id.get(),
                            amount=self.highest_bid.get(),
                        ),
                    ),
                ),
            ),
            self.highest_bidder_address.set(bid.get().sender()),
            self.highest_bid.set(bid.get().asset_amount()),
        )

    @external(authorize=is_seller)
    def accept_bid(self) -> Expr:
        """
        The seller may choose to accept the current highest bid and end the auction early.

        Asserts
        -------
        1. auction status == Committed
        2. there is a bid
        3. auction has not ended

        """
        return Seq(
            Assert(
                self.status.get() == Int(AuctionStatus.COMMITTED.value),
                self.highest_bid.get() > Int(0),
                Global.latest_timestamp() <= self.end_time.get(),
            ),
            self.status.set(Int(AuctionStatus.BID_ACCEPTED.value)),
        )

    @external(read_only=True)
    def latest_timestamp(self, *, output: abi.Uint64) -> Expr:
        """
        Get the latest confirmed block UNIX timestamp
        """
        return output.set(Global.latest_timestamp())

    @external
    def finalize(self, asset: abi.Asset, close_to: abi.Account) -> Expr:
        """
        Once the auction has ended, call finalize for each asset held by the Auction.

        If the auction ended sold, then
        - highest bidder account must be paired with auction assets
        - seller account must be paired with the bid asset

        If the auction ended not sold, then
        - highest bidder account must be paired with the bid asset
        - seller account must be paired with auction assets

        When all assets have been closed out, then the auction status is set to 'Finalized'.

        If the auction has already been fully finalized, i.e., status==Finalized, then the call will be rejected.

        """

        def is_sold() -> Expr:
            return Or(
                self.is_bid_accepted(),
                And(
                    self.status.get() == Int(AuctionStatus.COMMITTED.value),
                    Global.latest_timestamp() > self.end_time.get(),
                    self.highest_bid.get() > Int(0),
                ),
            )

        def handle_sold() -> Expr:
            return Seq(
                Assert(
                    Or(
                        And(
                            close_to.address() == self.seller_address.get(),
                            asset.asset_id() == self.bid_asset_id.get(),
                        ),
                        And(
                            close_to.address() == self.highest_bidder_address,
                            asset.asset_id() != self.bid_asset_id.get(),
                        ),
                    )
                ),
                execute_optout(asset, close_to),
            )

        def is_not_sold() -> Expr:
            return Or(
                self.is_cancelled(),
                And(
                    self.status.get() == Int(AuctionStatus.COMMITTED.value),
                    Global.latest_timestamp() > self.end_time.get(),
                    self.highest_bid.get() == Int(0),
                ),
            )

        def handle_not_sold() -> Expr:
            return Seq(
                Assert(close_to.address() == self.seller_address.get()),
                execute_optout(asset, close_to),
            )

        def close_out_asset() -> Expr:
            return Seq(
                Cond(
                    [is_sold(), handle_sold()],
                    [is_not_sold(), handle_not_sold()],
                ),
                total_assets := AccountParam.totalAssets(self.address),
                If(
                    total_assets.value() == Int(0),  # all assets have been closed out
                    self.status.set(Int(AuctionStatus.FINALIZED.value)),
                ),
            )

        return If(
            self.is_finalized(),
            Reject(),
            close_out_asset(),
        )

    def _assert_no_freeze_clawback(self, asset: abi.Asset) -> Expr:
        return Seq(
            freeze_address := asset.params().freeze_address(),
            Assert(
                Or(
                    Not(freeze_address.hasValue()),
                    freeze_address.value() == Global.zero_address(),
                )
            ),
            clawback_address := asset.params().clawback_address(),
            Assert(
                Or(
                    Not(clawback_address.hasValue()),
                    clawback_address.value() == Global.zero_address(),
                )
            ),
        )


def auction_storage_fees() -> MicroAlgos:
    """
    Computes Auction contract storage fees required to be reserved by the creator's account.

    The Auction creator's Algorand account's min balance requirement will increase by this amount.
    :return:
    """

    account_base_fee = int(0.1 * algo)
    per_state_entry_fee = int(0.025 * algo)
    per_state_int_entry_fee = int(0.0035 * algo)
    per_state_byte_slice_entry_fee = int(0.025 * algo)

    global_declared_state: dict[str, Any] = Auction().application_spec()["schema"][
        "global"
    ]["declared"]
    total_state_entries = len(global_declared_state)
    total_int_entries = len(
        [entry for entry in global_declared_state.values() if entry["type"] == "uint64"]
    )
    total_byte_slice_entries = total_state_entries - total_int_entries

    return MicroAlgos(
        account_base_fee
        + (per_state_entry_fee * total_state_entries)
        + (per_state_int_entry_fee * total_int_entries)
        + (per_state_byte_slice_entry_fee * total_byte_slice_entries)
    )
