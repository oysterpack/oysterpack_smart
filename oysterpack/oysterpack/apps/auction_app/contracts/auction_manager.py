from typing import Final

from algosdk.transaction import OnComplete
from beaker import Application, AppPrecompile, ApplicationStateValue, external
from beaker.application import get_method_signature
from beaker.decorators import create
from pyteal import (
    Expr,
    InnerTxnBuilder,
    Txn,
    Seq,
    TealType,
    TxnField,
    Int,
    Assert,
    InnerTxn,
    TxnType,
)
from pyteal.ast import abi

from oysterpack.apps.auction_app.contracts.auction import Auction, auction_storage_fees


class AuctionManager(Application):
    auction: Final[AppPrecompile] = AppPrecompile(Auction())

    auction_min_balance: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        static=True,
        descr="Auction contract min balance requirement that is paid by the seller when creating the Auction contract",
    )

    @create
    def create(self) -> Expr:
        """
        Creates an instance of the Auction contract to determine its minimum required balance.

        Notes
        -----
        - inner transactions
            - Auction contract creation
            - Auction contract deletion
        """
        return super().initialize_application_state()

    @external(read_only=True)
    def get_auction_creation_fees(self, *, output: abi.Uint64) -> Expr:
        """
        Returns the ALGO fees (in microalgos) required to create an Auction.
        """
        return output.set(Int(auction_storage_fees()))

    @external
    def create_auction(
        self, storage_fees: abi.PaymentTransaction, *, output: abi.Uint64
    ) -> Expr:
        """
        Creates a new Auction contract for the seller. The transaction sender is the seller.
        1. Create new Auction contract for the seller
        2. Verify payment is attached that will cover the auction storage fees

        Asserts
        -------
        1. Payment receiver is this contract
        2. Payment amount matches exactly the auction creation fees

        Notes
        -----
        - transaction fees = 0.002

        """
        return Seq(
            Assert(
                storage_fees.get().receiver() == self.address,
                storage_fees.get().amount() == Int(auction_storage_fees()),
            ),
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=None,
                method_signature=get_method_signature(Auction.create),
                args=[Txn.sender()],
                extra_fields=self.auction.get_create_config() | {TxnField.fee: Int(0)},
            ),
            output.set(InnerTxn.created_application_id()),
        )

    @external
    def delete_finalized_auction(self, auction: abi.Application) -> Expr:
        """
        Inner Transactions
        ------------------
        1. Close out Auction ALGO account to this contract
        2. Delete the Auction contract

        Notes
        -----
        - Auction contract must have been created by this contract.
        - Auction status must be `Finalized
        - When Auction contract is deleted, its ALGO account is closed out to this contract
        - Transaction fees = 0.003 ALGO

        """
        return InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.application_id: auction.application_id(),
                TxnField.on_completion: Int(OnComplete.DeleteApplicationOC.value),
                TxnField.fee: Int(0),
            }
        )
