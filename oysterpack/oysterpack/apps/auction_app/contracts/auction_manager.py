from typing import Final

from beaker import Application, AppPrecompile, ApplicationStateValue, external
from beaker.application import get_method_signature
from beaker.decorators import create, internal
from pyteal import (
    Expr,
    InnerTxnBuilder,
    Txn,
    Seq,
    TealType,
    AccountParam,
    TxnField,
    Int,
    InnerTxn,
    Assert,
    TxnType,
    OnComplete,
)
from pyteal.ast import abi

from oysterpack.apps.auction_app.contracts.auction import Auction


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

    def get_auction_min_balance(self, *, output: abi.Uint64) -> Expr:
        return output.set(
            self.auction_min_balance.get_else(
                Seq(
                    previous_min_balance := AccountParam.minBalance(
                        self.address
                    ).value(),
                    self._create_auction_contract(),
                    self.auction_min_balance.set(
                        AccountParam.minBalance(self.address).value()
                        - previous_min_balance
                    ),
                    # delete Auction contract
                    InnerTxnBuilder.ExecuteMethodCall(
                        app_id=InnerTxn.created_application_id(),
                        method_signature=get_method_signature(Auction.delete),
                        args=[],
                    ),
                    InnerTxnBuilder.Execute(
                        {
                            TxnField.type_enum: TxnType.ApplicationCall,
                            TxnField.application_id: InnerTxn.created_application_id(),
                            TxnField.on_completion: OnComplete.DeleteApplication,
                            TxnField.fee: Int(0),
                        }
                    ),
                )
            )
        )

    @external
    def create_auction(self, auction_storage_fees: abi.PaymentTransaction) -> Expr:
        """
        Creates a new Auction contract for the seller. The transaction sender is the seller.
        1. Create new Auction contract for the seller
        2. Verify payment is attached that will cover the auction storage fees
        :return:
        """
        return Seq(
            Assert(
                auction_storage_fees.get().receiver() == self.address,
                comment="payment receiver must be this contract",
            ),
            self._create_auction_contract(),
        )

    @internal
    def _create_auction_contract(self) -> Expr:
        return InnerTxnBuilder.ExecuteMethodCall(
            app_id=None,
            method_signature=get_method_signature(Auction.create),
            args=[Txn.sender()],
            extra_fields=self.auction.get_create_config() | {TxnField.fee: Int(0)},
        )
