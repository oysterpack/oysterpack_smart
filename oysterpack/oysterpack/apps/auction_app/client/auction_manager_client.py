"""
Auction Manager application client
"""
from typing import cast, Final

from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    TransactionWithSigner,
    ABIResult,
)
from algosdk.v2client.algod import AlgodClient
from beaker.application import get_method_signature
from beaker.client import ApplicationClient
from beaker.consts import algo

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.algorand.client.transactions import create_lease
from oysterpack.algorand.client.transactions.note import AppTxnNote
from oysterpack.algorand.client.transactions.payment import transfer_algo, MicroAlgos
from oysterpack.apps.auction_app.client.auction_client import AuctionClient
from oysterpack.apps.auction_app.contracts.auction import auction_storage_fees, Auction
from oysterpack.apps.auction_app.contracts.auction_manager import AuctionManager
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.client import AppClient


class AuctionManagerClient(AppClient):
    """
    AuctionManager application client
    """

    GET_AUCTION_CREATION_FEES_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(AuctionManager.get_auction_creation_fees),
    )

    CREATE_AUCTION_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(AuctionManager.create_auction),
    )

    DELETE_FINALIZED_AUCTION_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(AuctionManager.delete_finalized_auction),
    )

    WITHDRAW_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(AuctionManager.withdraw_algo),
    )

    def __init__(self, app_client: ApplicationClient):
        if app_client.app_id == 0:
            raise AssertionError("ApplicationClient.app_id must not be 0")

        if not isinstance(app_client.app, AuctionManager):
            raise AssertionError(
                "ApplicationClient.app must be an instance of AuctionManager"
            )

        super().__init__(app_client)

    def copy(
        self,
        signer: TransactionSigner | None = None,
        sender: Address | None = None,
    ):
        """
        Makes a copy of this client allowing the sender and signer to be overridden.
        """
        return AuctionManagerClient(
            self._app_client.prepare(sender=sender, signer=signer)
        )

    def get_auction_creation_fees(self) -> MicroAlgos:
        """
        :return: Auction storage fees that are requires to create an Auction app instance
        """
        return MicroAlgos(
            self._app_client.call(
                AuctionManager.get_auction_creation_fees,
                note=self.GET_AUCTION_CREATION_FEES_NOTE.encode(),
            ).return_value
        )

    def create_auction(self) -> AuctionClient:
        """
        Used by sellers to create a new Auction instance.
        """

        payment_txn = transfer_algo(
            sender=Address(cast(str, self._app_client.sender)),
            receiver=self.contract_address,
            amount=MicroAlgos(auction_storage_fees()),
            suggested_params=self.suggested_params(),
        )

        auction_app_id = self._app_client.call(
            AuctionManager.create_auction,
            storage_fees=TransactionWithSigner(
                payment_txn,
                cast(TransactionSigner, self._app_client.signer),
            ),
            suggested_params=self.suggested_params(txn_count=2),
            lease=create_lease(),
            note=self.CREATE_AUCTION_NOTE.encode(),
        ).return_value

        return AuctionClient(
            self._app_client.prepare(app=Auction(), app_id=auction_app_id)
        )

    def delete_finalized_auction(self, app_id: AppId) -> ABIResult:
        """
        Deletes the finalized Auction for the specified app ID.

        When the Auction is deleted, its account will be closed out to this AuctionManager's account to collect
        the Auction storage fees.

        :param app_id: Auction AppId
        """

        auction_client = AuctionClient(
            self._app_client.prepare(app=Auction(), app_id=app_id)
        )
        auction_state = auction_client.get_auction_state()
        if auction_state.status != AuctionStatus.FINALIZED:
            raise AssertionError("auction is not finalized")

        return self._app_client.call(
            AuctionManager.delete_finalized_auction,
            auction=app_id,
            suggested_params=self.suggested_params(txn_count=3),
            note=self.DELETE_FINALIZED_AUCTION_NOTE.encode(),
        )

    def get_treasury_balance(self) -> MicroAlgos:
        """
        The treasury balance is the ALGO balance amount above the AuctionManager's min balance.
        """
        app_account_info = self.get_application_account_info()
        balance: int = app_account_info["amount"]
        min_balance: int = app_account_info["min-balance"]
        return MicroAlgos(balance - min_balance)

    def withdraw(self, amount: MicroAlgos | None = None) -> ABIResult | None:
        """
        Can only be invoked by the AuctionManager creator account.

        :param amount: if no amount is specified, then the full available amount will be withdrawn
        :return: if amount
        """

        treasury_balance = self.get_treasury_balance()
        if amount is None:
            amount = treasury_balance

        if amount == 0:
            return None

        if amount > treasury_balance:
            raise AssertionError(
                f"Insufficient funds in treasury to fullfill withdrawal. Current treasury balance is {treasury_balance}"
            )

        return self._app_client.call(
            AuctionManager.withdraw_algo,
            amount=amount,
            suggested_params=self.suggested_params(txn_count=2),
            note=self.WITHDRAW_NOTE.encode(),
        )


def create_auction_manager(
    algod_client: AlgodClient,
    signer: TransactionSigner,
    creator: Address | None = None,
) -> AuctionManagerClient:
    """
    Creates an AuctionManager contract instance.

    The contract is funded with 0.1 ALGO

    :param creator: defaults to the sender associated with the signer
    :return : AuctionManagerClient for the AuctionManager contract that was created
    """
    app_client = ApplicationClient(
        client=algod_client,
        app=AuctionManager(),
        sender=creator,
        signer=signer,
    )
    app_client.create()
    app_client.fund(int(0.1 * algo))
    return AuctionManagerClient(app_client)
