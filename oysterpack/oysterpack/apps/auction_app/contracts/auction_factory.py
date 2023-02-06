from typing import Final

from beaker import Application, AppPrecompile, ApplicationStateValue
from beaker.decorators import create, external
from pyteal import (
    Expr,
    InnerTxnBuilder,
    TxnField,
    Txn,
    Seq,
    InnerTxn,
    AccountParam,
    AppParam,
    Assert,
    TealType,
    TxnType,
    OnComplete,
)
from pyteal.ast import abi

from oysterpack.apps.auction_app.contracts.auction import Auction


class AuctionFactory(Application):
    auction: Final[AppPrecompile] = AppPrecompile(Auction())
    auction_min_balance: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        static=True,
        descr="Auction contract min balance requirement that is paid by the seller when creating the Auction contract",
    )

    @create
    def create(self) -> Expr:
        create_config = self.auction.get_create_config()
        create_config[TxnField.accounts] = [self.address]
        return Seq(
            super().initialize_application_state(),
            # store Auction min balance
            previous_min_balance := AccountParam.minBalance(self.address).value(),
            InnerTxnBuilder.Execute(create_config),
            current_min_balance := AccountParam.minBalance(self.address).value(),
            self.auction_min_balance.set(current_min_balance - previous_min_balance),
            # delete Auction contract
            auction_app_id := InnerTxn.application_id(),
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: auction_app_id,
                    TxnField.on_completion: OnComplete.DeleteApplication,
                }
            ),
        )

    @external
    def create_auction(self, auction_storage_fees: abi.PaymentTransaction) -> Expr:
        """
        Creates a new Auction contract for the seller. The transaction sender is the seller.
        1. Create new Auction contract for the seller
        2. Verify payment is attached that will cover the auction storage fees
        :return:
        """
        create_config = self.auction.get_create_config()
        create_config[TxnField.accounts] = [Txn.sender()]
        return Seq(
            InnerTxnBuilder.Execute(create_config),
            # verify payment transaction
            Assert(
                auction_storage_fees.get().receiver() == self.address,
                comment="payment must be sent to this contract",
            ),
            app_addess := AppParam.address(InnerTxn.application_id()).value(),
            auction_min_balance := AccountParam.minBalance(app_addess).value(),
            Assert(
                auction_storage_fees.get().amount() == auction_min_balance,
                comment="payment amount must exactly match Auction contract required minimum balance",
            ),
        )
