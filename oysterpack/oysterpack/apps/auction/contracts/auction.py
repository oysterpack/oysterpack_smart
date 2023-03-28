"""
Auction smart contract

Auction is used to sell asset holdings escrowed by this contract to the highest bidder.

Seller must fund the Auction contract with ALGO to pay for contract storage costs:
- 0.1 ALGO for base contract storage cost
- 0.1 ALGO for each asset holding storage costs

When the auction is finalized, the ALGO paid for storage costs will be closed out to the creator address.
"""

from typing import Final, Any

from beaker.application import Application
from beaker.application_specification import ApplicationSpecification
from beaker.consts import algo
from beaker.decorators import Authorize
from beaker.state import GlobalStateValue
from pyteal import (
    TealType,
    Expr,
    Seq,
    Int,
    Global,
    AssetHolding,
    InnerTxnBuilder,
    Assert,
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
from oysterpack.apps.auction.contracts.auction_status import AuctionStatus


class AuctionState:
    """
    Auction contract state
    """

    # pylint: disable=invalid-name

    status: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(AuctionStatus.NEW.value),
    )

    seller_address: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        static=True,
    )

    bid_asset_id: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="Asset that is used to submit bids, i.e., the asset that the seller is accepting as payment",
    )
    min_bid: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="Minimum bid price that the seller will accept.",
    )

    highest_bidder_address: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes
    )
    highest_bid: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )

    # NOTE: The latest confirmed block UNIX timestamp is used on-chain (Global.latest_timstamp()).
    start_time: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="Auction start time specified as a UNIX timestamp.",
    )
    end_time: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="Auction end time specified as a UNIX timestamp.",
    )

    def is_new(self) -> Expr:
        """
        :return: True if status is New
        """
        return self.status == Int(AuctionStatus.NEW.value)

    def is_committed(self) -> Expr:
        """
        :return: True if status is Committed
        """
        return self.status == Int(AuctionStatus.COMMITTED.value)

    def is_bid_accepted(self) -> Expr:
        """
        :return: True if status is BidAccepted
        """
        return self.status == Int(AuctionStatus.BID_ACCEPTED.value)

    def is_cancelled(self) -> Expr:
        """
        :return: True if status is Cancelled
        """
        return self.status == Int(AuctionStatus.CANCELLED.value)

    def is_finalized(self) -> Expr:
        """
        :return: True if status is Finalized
        """
        return self.status == Int(AuctionStatus.FINALIZED.value)


APP_NAME: Final[str] = "oysterpack.auction"

app = Application(
    APP_NAME,
    state=AuctionState(),
)

app_spec: ApplicationSpecification = app.build()


@app.create
def create(seller: abi.Account) -> Expr:  # pylint: disable=arguments-differ
    """
    Initializes the application global state.

    - seller address is stored in global state
    - initial status will be AuctionStatus.New

    """
    return Seq(
        app.initialize_global_state(),
        app.state.seller_address.set(seller.address()),
    )


@app.delete(authorize=Authorize.only_creator(), bare=True)
def delete() -> Expr:
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
        Assert(app.state.is_finalized()),
        # assert that the app has opted out of all assets
        total_assets := AccountParam.totalAssets(Global.current_application_address()),
        Assert(total_assets.value() == Int(0)),
        # close out ALGO balance to the creator
        InnerTxnBuilder.Execute(payment.close_out(Global.creator_address())),
    )


@app.external(read_only=True)
def app_name(*, output: abi.String) -> Expr:
    """
    Returns the application name
    """
    return output.set(APP_NAME)


@app.external(authorize=Authorize.only(app.state.seller_address))
def set_bid_asset(bid_asset: abi.Asset, min_bid: abi.Uint64) -> Expr:
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
            app.state.is_new(),
            min_bid.get() > Int(0),
            Or(
                app.state.bid_asset_id == Int(0),
                app.state.bid_asset_id == bid_asset.asset_id(),
            ),
        ),
        _assert_no_freeze_clawback(bid_asset),
        app.state.bid_asset_id.set(bid_asset.asset_id()),
        app.state.min_bid.set(min_bid.get()),
        # if the auction does not hold the bid asset, then opt in the bid asset
        bid_asset_holding := AssetHolding.balance(
            Global.current_application_address(),
            bid_asset.asset_id(),
        ),
        If(
            Not(bid_asset_holding.hasValue()),
            execute_optin(bid_asset),
        ),
    )


@app.external(authorize=Authorize.only(app.state.seller_address))
def optin_asset(asset: abi.Asset) -> Expr:
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
        Assert(app.state.is_new()),
        _assert_no_freeze_clawback(asset),
        execute_optin(asset),
    )


@app.external(authorize=Authorize.only(app.state.seller_address))
def optout_asset(asset: abi.Asset) -> Expr:
    """
    Closes out the asset to the seller

    Asserts
    -------
    1. auction status is `New`
    """

    return Seq(
        Assert(app.state.is_new()),
        execute_optout(asset, Txn.sender()),
        # If the bid asset is being opted out, then reset `bid_set_id` to zero
        # NOTE: in order to change the bid asset, it must first be opted out.
        If(
            asset.asset_id() == app.state.bid_asset_id,
            app.state.bid_asset_id.set(Int(0)),
        ),
    )


@app.external(authorize=Authorize.only(app.state.seller_address))
def withdraw_asset(asset: abi.Asset, amount: abi.Uint64) -> Expr:
    """
    Assets can only be withdrawn when auction status is `New`

    Notes
    -----
    - transaction fees = 0.002 ALGO
    """
    return Seq(
        Assert(app.state.is_new()),
        execute_transfer(Txn.sender(), asset, amount),
    )


@app.external(authorize=Authorize.only(app.state.seller_address))
def commit(start_time: abi.Uint64, end_time: abi.Uint64) -> Expr:
    """
    When the seller is done setting up the auction, the final step is to commit the auction.
    Once the auction is committed, it can no longer be changed.

    :param start_time: when the bidding session starts - time must be >= Global.latest_timestamp() - Int(10)
    :param end_time: when the bidding session ends
    """
    return Seq(
        Assert(
            app.state.is_new(),
            app.state.bid_asset_id != Int(0),
            app.state.min_bid > Int(0),
        ),
        # besides the bid asset, there should be at least 1 asset for sale
        #
        # NOTE:
        # - asset balances should be > 0, but are not checked here
        # - client should check the asset balances before committing
        total_assets := AccountParam.totalAssets(Global.current_application_address()),
        Assert(
            total_assets.value() > Int(1),
            start_time.get() >= Global.latest_timestamp(),
            end_time.get() > start_time.get(),
        ),
        app.state.start_time.set(start_time.get()),
        app.state.end_time.set(end_time.get()),
        app.state.status.set(Int(AuctionStatus.COMMITTED.value)),
    )


@app.external(authorize=Authorize.only(app.state.seller_address))
def cancel() -> Expr:
    """
    The auction cannot be cancelled once it has been committed.

    - If the auction is already cancelled, then this is a noop.

    :return:
    """

    handle_is_new = Seq(
        total_assets := AccountParam.totalAssets(Global.current_application_address()),
        If(
            total_assets.value() == Int(0),  # all assets have been closed out
            app.state.status.set(Int(AuctionStatus.FINALIZED.value)),
            app.state.status.set(Int(AuctionStatus.CANCELLED.value)),
        ),
    )

    return Cond(
        [app.state.is_new(), handle_is_new],
        [app.state.is_cancelled(), Approve()],
    )


@app.external
def submit_bid(
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
            app.state.status == Int(AuctionStatus.COMMITTED.value),
            # check auction bidding has started
            Global.latest_timestamp() >= app.state.start_time,
            Global.latest_timestamp() <= app.state.end_time,
            bid.get().asset_receiver() == Global.current_application_address(),
            bid.get().xfer_asset() == app.state.bid_asset_id,
            bid.get().asset_amount() > app.state.highest_bid,
        ),
        # refund the current highest bidder
        # if this is the first bid (highes_bid == 0), then no refund is needed
        If(
            app.state.highest_bid > Int(0),
            Seq(
                Assert(
                    highest_bidder.address() == app.state.highest_bidder_address,
                    bid_asset.asset_id() == app.state.bid_asset_id,
                ),
                bid_asset_holding := AssetHolding.balance(
                    highest_bidder.address(), bid_asset.asset_id()
                ),
                If(
                    bid_asset_holding.hasValue(),
                    execute_transfer(
                        receiver=highest_bidder,
                        asset=app.state.bid_asset_id,
                        amount=app.state.highest_bid,
                    ),
                ),
            ),
        ),
        app.state.highest_bidder_address.set(bid.get().sender()),
        app.state.highest_bid.set(bid.get().asset_amount()),
    )


@app.external(authorize=Authorize.only(app.state.seller_address))
def accept_bid() -> Expr:
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
            app.state.status == Int(AuctionStatus.COMMITTED.value),
            app.state.highest_bid > Int(0),
            Global.latest_timestamp() <= app.state.end_time,
        ),
        app.state.status.set(Int(AuctionStatus.BID_ACCEPTED.value)),
    )


@app.external
def finalize(asset: abi.Asset, close_to: abi.Account) -> Expr:
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
            app.state.is_bid_accepted(),
            And(
                app.state.status == Int(AuctionStatus.COMMITTED.value),
                Global.latest_timestamp() > app.state.end_time,
                app.state.highest_bid > Int(0),
            ),
        )

    def handle_sold() -> Expr:
        return Seq(
            Assert(
                Or(
                    And(
                        close_to.address() == app.state.seller_address,
                        asset.asset_id() == app.state.bid_asset_id,
                    ),
                    And(
                        close_to.address() == app.state.highest_bidder_address,
                        asset.asset_id() != app.state.bid_asset_id,
                    ),
                )
            ),
            execute_optout(asset, close_to),
        )

    def is_not_sold() -> Expr:
        return Or(
            app.state.is_cancelled(),
            And(
                app.state.status == Int(AuctionStatus.COMMITTED.value),
                Global.latest_timestamp() > app.state.end_time,
                app.state.highest_bid == Int(0),
            ),
        )

    def handle_not_sold() -> Expr:
        return Seq(
            Assert(close_to.address() == app.state.seller_address),
            execute_optout(asset, close_to),
        )

    def close_out_asset() -> Expr:
        return Seq(
            Cond(
                [is_sold(), handle_sold()],
                [is_not_sold(), handle_not_sold()],
            ),
            total_assets := AccountParam.totalAssets(
                Global.current_application_address()
            ),
            If(
                total_assets.value() == Int(0),  # all assets have been closed out
                app.state.status.set(Int(AuctionStatus.FINALIZED.value)),
            ),
        )

    return If(
        app.state.is_finalized(),
        Reject(),
        close_out_asset(),
    )


@app.external(read_only=True)
def latest_timestamp(*, output: abi.Uint64) -> Expr:
    """
    Get the latest confirmed block UNIX timestamp
    """
    return output.set(Global.latest_timestamp())


def _assert_no_freeze_clawback(asset: abi.Asset) -> Expr:
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

    global_declared_state: dict[str, Any] = app.build().schema["global"]["declared"]
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
