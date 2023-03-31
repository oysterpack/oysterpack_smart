"""
Auction application client
"""
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import StrEnum
from typing import cast, Final, Any

from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    AtomicTransactionComposer,
    TransactionWithSigner,
    ABIResult,
)
from algosdk.constants import ZERO_ADDRESS
from algosdk.encoding import encode_address
from algosdk.error import AlgodHTTPError
from beaker.client.application_client import ApplicationClient

from oysterpack.algorand.client.assets.asset_config import AssetConfig
from oysterpack.algorand.client.model import (
    Address,
    AssetId,
    AssetHolding,
    MicroAlgos,
    TxnId,
)
from oysterpack.algorand.client.transactions import create_lease, asset
from oysterpack.algorand.client.transactions.asset import opt_in
from oysterpack.algorand.client.transactions.note import AppTxnNote
from oysterpack.algorand.params import MinimumBalance
from oysterpack.apps.auction.client.errors import AuthError
from oysterpack.apps.auction.contracts import auction
from oysterpack.apps.auction.contracts.auction import (
    AuctionState as ContractAuctionState,
)
from oysterpack.apps.auction.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction.domain.auction_state import AuctionState
from oysterpack.apps.client import AppClient


@dataclass(slots=True)
class InvalidAssetId(Exception):
    """Raised for invalid asset ID"""

    asset_id: AssetId


def to_auction_state(state: dict[bytes | str, bytes | str | int]) -> AuctionState:
    """
    maps raw global state data to an AuctionState
    """

    def to_address(hex_encoded_address_bytes: str) -> Address:
        """
        Helper function to encode an address stored in the app's global state as a standard Algorand address.

        Notes
        -----
        - seller address is stored as bytes in the contract
        - beaker's ApplicationClient will return the bytes as a hex encoded string

        :param hex_encoded_address_bytes:
        :return:
        """
        return Address(encode_address(bytes.fromhex(hex_encoded_address_bytes)))

    def status() -> AuctionStatus:
        match state[ContractAuctionState.status.str_key()]:
            case AuctionStatus.NEW.value:
                return AuctionStatus.NEW
            case AuctionStatus.CANCELLED.value:
                return AuctionStatus.CANCELLED
            case AuctionStatus.COMMITTED.value:
                return AuctionStatus.COMMITTED
            case AuctionStatus.BID_ACCEPTED.value:
                return AuctionStatus.BID_ACCEPTED
            case AuctionStatus.FINALIZED.value:
                return AuctionStatus.FINALIZED
            case _:
                raise ValueError(state[ContractAuctionState.status.str_key()])

    def seller_address() -> Address:
        return to_address(
            cast(str, state[ContractAuctionState.seller_address.str_key()])
        )

    def bid_asset_id() -> AssetId | None:
        if ContractAuctionState.bid_asset_id.str_key() in state.keys():
            return AssetId(
                cast(int, state[ContractAuctionState.bid_asset_id.str_key()])
            )
        return None

    def min_bid() -> int | None:
        if ContractAuctionState.min_bid.str_key() in state.keys():
            return cast(int, state[ContractAuctionState.min_bid.str_key()])
        return None

    def highest_bidder_address() -> Address | None:
        if ContractAuctionState.highest_bidder_address.str_key() in state.keys():
            value = cast(
                str, state[ContractAuctionState.highest_bidder_address.str_key()]
            )
            return to_address(value) if value else None
        return None

    def highest_bid() -> int:
        if ContractAuctionState.highest_bid.str_key() in state.keys():
            return cast(int, state[ContractAuctionState.highest_bid.str_key()])
        return 0

    def start_time() -> datetime | None:
        if ContractAuctionState.start_time.str_key() in state.keys():
            value = cast(int, state[ContractAuctionState.start_time.str_key()])
            return datetime.fromtimestamp(value, UTC) if value else None
        return None

    def end_time() -> datetime | None:
        if ContractAuctionState.end_time.str_key() in state.keys():
            value = cast(int, state[ContractAuctionState.end_time.str_key()])
            return datetime.fromtimestamp(value, UTC) if value else None
        return None

    return AuctionState(
        status=status(),
        seller=seller_address(),
        bid_asset_id=bid_asset_id(),
        min_bid=min_bid(),
        highest_bidder=highest_bidder_address(),
        highest_bid=highest_bid(),
        start_time=start_time(),
        end_time=end_time(),
    )


class _AuctionClient(AppClient):
    def __init__(self, app_client: ApplicationClient):
        if app_client.app_id == 0:
            raise AssertionError("ApplicationClient.app_id must not be 0")

        # TODO: is there a more robust way
        if app_client._app_client.app_spec.contract.name != auction.app.name:
            raise AssertionError(
                f"contract name does not match: {app_client._app_client.app_spec.contract.name} != {auction.app.name}"
            )

        super().__init__(app_client)

    def _fund_asset_optin(self):
        """
        Ensures the contract is funded to be able to opt in an asset
        :return:
        """
        account_info = self.get_application_account_info()
        algo_balance = cast(int, account_info["amount"])
        min_balance = cast(int, account_info["min-balance"])
        self.fund(MicroAlgos(min_balance + MinimumBalance.ASSET_OPT_IN - algo_balance))

    def _assert_valid_asset_id(self, asset_id: AssetId):
        asset_config = AssetConfig.get_asset_info(asset_id, self._app_client.client)
        if asset_config is None:
            raise InvalidAssetId(asset_id)
        if asset_config.clawback is not None or asset_config.freeze is not None:
            raise AssertionError("asset must not have clawback or freeze")

    def _is_asset_opted_in(self, asset_id: AssetId) -> bool:
        try:
            self._app_client.client.account_asset_info(self.contract_address, asset_id)
            # if the call successfully returns, then it means the Auction already holds the asset
            return True
        except AlgodHTTPError as err:
            if err.code == 404:
                return False
            raise err

    def _get_asset_holding(self, asset_id) -> AssetHolding:
        """
        Raises an exception if the Auction does not hold the asset
        """
        return AssetHolding.from_data(
            cast(
                dict[str, Any],
                self._app_client.client.account_asset_info(
                    self.contract_address, asset_id
                ),
            )
        )


class _AuctionClientSupport(AppClient):
    def get_auction_state(self) -> AuctionState:
        """
        :return: AuctionState
        """
        return to_auction_state(self.get_application_state())

    def get_auction_assets(self) -> list[AssetHolding]:
        """
        The auction's assets that are for sale are returned, i.e., all asset holdings excluding the bid asset.

        :return: list[AssetHolding]
        """
        auction_assets = [
            AssetHolding.from_data(asset)
            for asset in self.get_application_account_info()["assets"]
        ]
        bid_asset_id = self.get_auction_state().bid_asset_id
        if bid_asset_id:
            return [asset for asset in auction_assets if asset.asset_id != bid_asset_id]
        return auction_assets

    def get_bid_asset_holding(self) -> AssetHolding | None:
        """
        :return: None if the bid asset is not configured
        """
        bid_asset_id = self.get_auction_state().bid_asset_id
        if bid_asset_id is None:
            return None
        try:
            bid_asset_holding = self._app_client.client.account_asset_info(
                self.contract_address, bid_asset_id
            )
            return AssetHolding.from_data(cast(dict[str, Any], bid_asset_holding))
        except AlgodHTTPError as err:
            if err.code == 404:
                return None
            raise


class AuctionPhase(StrEnum):
    """
    Defines Auction contract method phases.

    Used to augment Auction contract transaction notes
    """

    # tags transactions that in the auction setup phase
    # ----------------------------------------------------
    # AuctionClient.SET_BID_ASSET_NOTE
    # AuctionClient.SET_BID_ASSET_NOTE
    # AuctionClient.OPTIN_ASSET_NOTE
    # AuctionClient.OPTOUT_ASSET_NOTE
    # AuctionClient.DEPOSIT_ASSET_NOTE
    # AuctionClient.WITHDRAW_ASSET_NOTE
    SETUP = "setup"

    # tags transactions that are in the auction bidding phase
    # -------------------------------------------------------
    # COMMIT_NOTE
    # ACCEPT_BID_NOTE
    # AuctionBidder.BID_NOTE
    BIDDING = "bidding"


# TODO: logging
class AuctionBidder(_AuctionClientSupport):
    """
    Auction client used for placing bids.
    """

    BID_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.submit_bid.method_signature(),
        group=AuctionPhase.BIDDING,
    )

    OPTIN_AUCTION_ASSETS_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method="optin_auction_assets",
    )

    def __init__(self, app_client: ApplicationClient):
        if app_client.app_id == 0:
            raise AssertionError("ApplicationClient.app_id must not be 0")

        # TODO: is there a more robust way
        if app_client._app_client.app_spec.contract.name != auction.APP_NAME:
            raise AssertionError(
                f"contract name does not match: {app_client._app_client.app_spec.contract.name} != {auction.app.name}"
            )

        super().__init__(app_client)

    def bid(self, amount: int) -> ABIResult:
        """
        Used to submit a bid.

        Notes
        -----
        - Auction bidding session must be open
        - The bid must be higher than the current highest bid.
        """
        auction_state = to_auction_state(self.get_application_state())
        if not auction_state.is_bidding_open():
            raise AssertionError("auction is not open for bidding")

        if amount <= auction_state.highest_bid:
            raise AssertionError(
                f"bid is too low - current highest bid is: {auction_state.highest_bid}"
            )

        asset_transfer_txn = asset.transfer(
            sender=cast(Address, self._app_client.sender),
            receiver=self.contract_address,
            asset_id=cast(AssetId, auction_state.bid_asset_id),
            amount=amount,
            suggested_params=self.suggested_params(),
        )

        suggested_params = self.suggested_params()

        if auction_state.highest_bidder:
            highest_bidder = auction_state.highest_bidder
            # transaction fees need to cover the inner transaction to refund the highest bidder
            suggested_params.fee = suggested_params.min_fee * 2  # type: ignore
        else:
            highest_bidder = Address(ZERO_ADDRESS)

        return self._app_client.call(
            auction.submit_bid,
            bid=TransactionWithSigner(
                asset_transfer_txn,
                cast(TransactionSigner, self._app_client.signer),
            ),
            highest_bidder=highest_bidder,
            bid_asset=auction_state.bid_asset_id,
            sender=self._app_client.sender,
            suggested_params=suggested_params,
            note=self.BID_NOTE.encode(),
        )

    def optin_auction_assets(self) -> list[TxnId]:
        """
        Opts in the bidder account into all the auction's assets.

        NOTE: if the bidder wins the auction, the bidder will need to opt in the auction's assets in order to be
              able to receive them.
        """
        bidder = cast(Address, self._app_client.sender)
        txids: list[TxnId] = []
        for auction_asset in self.get_auction_assets():
            try:
                self._app_client.client.account_asset_info(
                    bidder, auction_asset.asset_id
                )
            except AlgodHTTPError as err:
                if err.code == 404:  # bidder account is not opted in
                    txn = opt_in(
                        account=bidder,
                        asset_id=auction_asset.asset_id,
                        suggested_params=self.suggested_params(),
                        note=AuctionBidder.OPTIN_AUCTION_ASSETS_NOTE.encode(),
                    )
                    atc = AtomicTransactionComposer()
                    atc.add_transaction(
                        TransactionWithSigner(
                            txn, cast(TransactionSigner, self._app_client.signer)
                        )
                    )
                    result = atc.execute(self._app_client.client, 4)
                    txids += cast(list[TxnId], result.tx_ids)
                else:
                    raise

        return txids


# TODO: logging
class AuctionClient(_AuctionClient, _AuctionClientSupport):
    """
    Auction application client
    """

    SET_BID_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.set_bid_asset.method_signature(),
        group=AuctionPhase.SETUP,
    )

    OPTIN_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.optin_asset.method_signature(),
        group=AuctionPhase.SETUP,
    )

    OPTOUT_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.optout_asset.method_signature(),
        group=AuctionPhase.SETUP,
    )

    DEPOSIT_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method="deposit_asset",
        group=AuctionPhase.SETUP,
    )

    WITHDRAW_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.withdraw_asset.method_signature(),
        group=AuctionPhase.SETUP,
    )

    COMMIT_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.commit.method_signature(),
        group=AuctionPhase.BIDDING,
    )

    ACCEPT_BID_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.accept_bid.method_signature(),
        group=AuctionPhase.BIDDING,
    )

    CANCEL_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.cancel.method_signature(),
    )

    FINALIZE_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.finalize.method_signature(),
    )

    LATEST_TIMESTAMP_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=auction.APP_NAME,
        method=auction.latest_timestamp.method_signature(),
    )

    def get_seller_address(self) -> Address:
        """
        Returns auction seller address
        """
        return self.get_auction_state().seller

    def set_bid_asset(self, asset_id: AssetId, min_bid: int) -> ABIResult | None:
        """
        Sets or updates the bid asset settings.

        The bid asset must not have freeze or clawback settings

        :param asset_id:
        :param min_bid:
        :return: None is returned if there were no changes needed, i.e., no transaction was submitted
        """
        app_state = self.get_auction_state()
        if app_state.bid_asset_id == asset_id and app_state.min_bid == min_bid:
            # then no changes are needed
            return None

        if app_state.seller != self._app_client.sender:
            raise AuthError

        self._assert_valid_asset_id(asset_id)

        # if the bid asset is being updated, then opt out the bid asset
        if app_state.bid_asset_id and app_state.bid_asset_id != asset_id:
            self.optout_asset(app_state.bid_asset_id)

        # transaction fees need to cover the inner transaction to opt in the bid asset
        suggested_params = self.suggested_params(txn_count=2)

        # if only the min bid is being changed, then no bid asset opt in is needed
        if app_state.bid_asset_id and app_state.bid_asset_id == asset_id:
            suggested_params.fee = suggested_params.min_fee
        else:
            self._fund_asset_optin()

        return self._app_client.call(
            auction.set_bid_asset,
            bid_asset=asset_id,
            min_bid=min_bid,
            suggested_params=suggested_params,
            lease=create_lease(),
            note=self.SET_BID_ASSET_NOTE.encode(),
        )

    def optout_asset(self, asset_id: AssetId) -> ABIResult | None:
        """
        If the contract does not hold the asset, then this is a noop.

        Asserts
        -------
        1. sender is seller
        """

        if not self._is_asset_opted_in(asset_id):
            return None

        if self.get_seller_address() != self._app_client.sender:
            raise AuthError

        return self._app_client.call(
            auction.optout_asset,
            asset=asset_id,
            suggested_params=self.suggested_params(txn_count=2),
            lease=create_lease(),
            note=self.OPTOUT_ASSET_NOTE.encode(),
        )

    def optin_asset(self, asset_id: AssetId) -> ABIResult | None:
        """
        If the asset is not already opted in, then opt in the asset.
        Also makes sure the Auction contract is funded to opt in the asset.

        :return : None if the auction already holds the asset
        """

        if self.get_seller_address() != self._app_client.sender:
            raise AuthError

        self._assert_valid_asset_id(asset_id)

        if self._is_asset_opted_in(asset_id):
            return None

        self._fund_asset_optin()
        return self._app_client.call(
            auction.optin_asset,
            asset=asset_id,
            suggested_params=self.suggested_params(txn_count=2),
            lease=create_lease(),
            note=self.OPTIN_ASSET_NOTE.encode(),
        )

    def deposit_asset(self, asset_id: AssetId, amount: int) -> AssetHolding:
        """
        If necessary, the asset is opted in and the contract is funded.

        Asserts
        -------
        1. amount > 0
        2. auction status == New
        3. asset_id != bid_asset_id
        4. sender is seller

        :param asset_id: bid asset deposits are not allowed
        :param amount: must be > 0
        """

        # check args
        if amount <= 0:
            raise AssertionError("amount must be > 0")

        app_state = self.get_auction_state()
        if app_state.seller != self._app_client.sender:
            raise AuthError
        if app_state.status != AuctionStatus.NEW:
            raise AssertionError(
                "asset deposit is only allowed when auction status is 'New'"
            )

        if app_state.bid_asset_id == asset_id:
            raise AssertionError("asset deposits are not allowed for the bid asset")

        # ensure the auction has opted in the asset
        self.optin_asset(asset_id)

        # transfer the asset
        # the transfer will fail if there are insufficient funds
        asset_transfer_txn = asset.transfer(
            sender=Address(cast(str, self._app_client.sender)),
            receiver=self.contract_address,
            asset_id=asset_id,
            amount=amount,
            suggested_params=self.suggested_params(),
            note=self.DEPOSIT_ASSET_NOTE.encode(),
        )
        atc = AtomicTransactionComposer()
        self._app_client.add_transaction(atc, asset_transfer_txn)
        atc.execute(self._app_client.client, 4)

        return self._get_asset_holding(asset_id)

    def withdraw_asset(self, asset_id: AssetId, amount: int) -> AssetHolding:
        """
        Only the seller can withdraw assets

        Asserts
        -------
        1. sender is seller
        2. auction status is `New`
        3. amount > 0
        """

        if amount <= 0:
            raise AssertionError("amount must be > 0")

        app_state = self.get_auction_state()
        if app_state.seller != self._app_client.sender:
            raise AuthError

        if app_state.status != AuctionStatus.NEW:
            raise AssertionError(
                "asset withdrawal is only allowed when auction status is 'New'"
            )

        try:
            asset_balance = self._get_asset_holding(asset_id).amount
            if asset_balance < amount:
                raise AssertionError(
                    f"Auction has insufficient funds - asset balance is {asset_balance}"
                )
        except AlgodHTTPError as err:
            raise AssertionError("Auction does not hold the asset") from err

        self._app_client.call(
            auction.withdraw_asset,
            asset=asset_id,
            amount=amount,
            suggested_params=self.suggested_params(txn_count=2),
            note=self.WITHDRAW_ASSET_NOTE.encode(),
        )

        return self._get_asset_holding(asset_id)

    def commit(self, start_time: datetime | None, end_time: datetime) -> ABIResult:
        """
        Asserts
        -------
        1. end time > start time
        2. auction status == New
        3. bid asset has been set
        4. min bid > 0
        5. auction has at least 1 asset for sale
        6. auction asset balances > 0
        7. bid asset balance == 0

        :param start_time: defaults to now
        """

        if start_time is None:
            start_time = datetime.now(UTC)

        if int(end_time.timestamp()) <= int(start_time.timestamp()):
            raise AssertionError("end_time must be after start_time")

        app_state = self.get_auction_state()
        if app_state.seller != self._app_client.sender:
            raise AuthError

        if app_state.status != AuctionStatus.NEW:
            raise AssertionError(
                "auction can only be commited when auction status is 'New'"
            )

        if app_state.bid_asset_id is None:
            raise AssertionError("bid asset has not been set")

        if not app_state.min_bid:
            raise AssertionError("min must be greater than 0")

        auction_assets = self.get_auction_assets()
        if len(auction_assets) == 0:
            raise AssertionError("auction has no assets")

        for asset_holding in auction_assets:
            if asset_holding.amount == 0:
                raise AssertionError(
                    "all auction asset balances must be greater than 0"
                )

        if self._get_asset_holding(app_state.bid_asset_id).amount > 0:
            raise AssertionError("bid asset balance must be 0")

        return self._app_client.call(
            auction.commit,
            start_time=int(start_time.timestamp()),
            end_time=int(end_time.timestamp()),
            note=self.COMMIT_NOTE.encode(),
        )

    def accept_bid(self) -> ABIResult:
        """
        Enables the seller to accept a bid before the bidding session is over.
        """

        app_state = self.get_auction_state()
        if not app_state.is_bidding_open():
            raise AssertionError("bidding sesssion is not open")
        if app_state.highest_bid == 0:
            raise AssertionError("auction has no bid")

        return self._app_client.call(
            auction.accept_bid,
            note=self.ACCEPT_BID_NOTE.encode(),
        )

    def cancel(self) -> ABIResult:
        """
        Enables the seller to cancel the auction.

        Notes
        -----
        - an auction cannot be cancelled once it is committed
        - auction storage fees will not be refunded
        """

        app_state = self.get_auction_state()
        if app_state.status != AuctionStatus.NEW:
            raise AssertionError(
                "auction can only be commited when auction status is 'New'"
            )
        if app_state.seller != self._app_client.sender:
            raise AuthError

        return self._app_client.call(
            auction.cancel,
            note=AuctionClient.CANCEL_NOTE.encode(),
        )

    def finalize(self) -> list[ABIResult] | None:
        """
        Used to finalize the auction once it has reached an end state:
        - cancelled
        - bid accepted
        - bidding session is over

        :return: None if the auction is already finalized
        """

        app_state = self.get_auction_state()
        if app_state.status == AuctionStatus.FINALIZED:
            return None
        if not app_state.is_ended():
            raise AssertionError("auction cannot be finalized because it has not ended")

        suggested_params = self.suggested_params(txn_count=2)
        results: list[ABIResult] = []
        if app_state.is_sold():
            # close out auction assets to the highest bidder
            for auction_asset in self.get_auction_assets():
                results.append(
                    self._app_client.call(
                        auction.finalize,
                        asset=auction_asset.asset_id,
                        close_to=app_state.highest_bidder,
                        suggested_params=suggested_params,
                        lease=create_lease(),
                        note=self.FINALIZE_NOTE.encode(),
                    )
                )
            # close out the bid asset to the seller
            results.append(
                self._app_client.call(
                    auction.finalize,
                    asset=app_state.bid_asset_id,
                    close_to=app_state.seller,
                    suggested_params=suggested_params,
                    lease=create_lease(),
                    note=self.FINALIZE_NOTE.encode(),
                )
            )
        else:
            # close out auction assets to the seller
            for auction_asset in self.get_auction_assets():
                results.append(
                    self._app_client.call(
                        auction.finalize,
                        asset=auction_asset.asset_id,
                        close_to=app_state.seller,
                        suggested_params=suggested_params,
                        lease=create_lease(),
                        note=self.FINALIZE_NOTE.encode(),
                    )
                )
            if app_state.bid_asset_id:
                try:
                    self.get_bid_asset_holding()
                    results.append(
                        self._app_client.call(
                            auction.finalize,
                            asset=app_state.bid_asset_id,
                            close_to=app_state.seller,
                            suggested_params=suggested_params,
                            lease=create_lease(),
                            note=self.FINALIZE_NOTE.encode(),
                        )
                    )
                except AlgodHTTPError as err:
                    if err.code != 404:
                        raise
        return results

    def latest_timestamp(self) -> datetime:
        """
        The timestamp for the latest confirmed block that is used to determine the bidding session window.
        """
        result = self._app_client.call(
            auction.latest_timestamp,
            note=self.LATEST_TIMESTAMP_NOTE.encode(),
        )
        return datetime.fromtimestamp(result.return_value, UTC)
