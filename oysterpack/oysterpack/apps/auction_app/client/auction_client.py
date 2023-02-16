"""
Auction application client
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from pprint import pformat
from typing import cast, Final

from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    AtomicTransactionComposer,
    TransactionWithSigner,
    ABIResult,
)
from algosdk.constants import ZERO_ADDRESS
from algosdk.encoding import encode_address
from algosdk.error import AlgodHTTPError
from beaker.application import get_method_signature
from beaker.client import ApplicationClient

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
from oysterpack.apps.auction_app.client.errors import AuthError
from oysterpack.apps.auction_app.contracts.auction import Auction
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.client import AppClient


@dataclass
class InvalidAssetId(Exception):
    """Raised for invalid asset ID"""

    asset_id: AssetId


class AuctionState:
    """
    Auction application state
    """

    def __init__(self, state: dict[bytes | str, bytes | str | int]):
        """
        :param state: application state retrieved using AlgodClient
        """
        self.__state = state

    @property
    def status(self) -> AuctionStatus:
        """
        :return: AuctionStatus
        """
        match self.__state[Auction.status.str_key()]:
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
                raise ValueError(self.__state[Auction.status.str_key()])

    @property
    def seller_address(self) -> Address:
        """
        :return: Address
        """
        return self._encode_address(
            cast(str, self.__state[Auction.seller_address.str_key()])
        )

    @property
    def bid_asset_id(self) -> AssetId | None:
        """
        Bid asset is the asset that the seller is accepting as payment.

        :return: None means not configured
        """
        if Auction.bid_asset_id.str_key() in self.__state.keys():
            return AssetId(cast(int, self.__state[Auction.bid_asset_id.str_key()]))
        return None

    @property
    def min_bid(self) -> int | None:
        """
        The minimum bid that the seller will accept.

        :return: None means not configured
        """
        if Auction.min_bid.str_key() in self.__state.keys():
            return cast(int, self.__state[Auction.min_bid.str_key()])
        return None

    @property
    def highest_bidder_address(self) -> Address | None:
        """
        :return: Address | None
        """
        if Auction.highest_bidder_address.str_key() in self.__state.keys():
            value = cast(str, self.__state[Auction.highest_bidder_address.str_key()])
            return self._encode_address(value) if value else None
        return None

    @property
    def highest_bid(self) -> int:
        """
        :return: highest bid amount - zero means no bid yet
        """
        if Auction.highest_bid.str_key() in self.__state.keys():
            return cast(int, self.__state[Auction.highest_bid.str_key()])
        return 0

    @property
    def start_time(self) -> datetime | None:
        """
        When the bidding session starts.

        :return: None means not configured
        """
        if Auction.start_time.str_key() in self.__state.keys():
            value = cast(int, self.__state[Auction.start_time.str_key()])
            return datetime.fromtimestamp(value, UTC) if value else None
        return None

    @property
    def end_time(self) -> datetime | None:
        """
        When the bidding session ends.

        :return: None means not configured
        """
        if Auction.end_time.str_key() in self.__state.keys():
            value = cast(int, self.__state[Auction.end_time.str_key()])
            return datetime.fromtimestamp(value, UTC) if value else None
        return None

    def is_bidding_open(self) -> bool:
        """
        :return: True if the Auction is Committed and the current time is within the bidding session window.
        """
        if self.start_time and self.end_time:
            return (
                self.status == AuctionStatus.COMMITTED
                and self.start_time <= datetime.now(UTC) < self.end_time
            )
        return False

    def is_ended(self) -> bool:
        """
        :return: True if the auction has ended, but not yet fully finalized
        """
        if self.status in [
            AuctionStatus.BID_ACCEPTED,
            AuctionStatus.CANCELLED,
        ]:
            return True

        return (
            self.status == AuctionStatus.COMMITTED
            # if status is committed, then `end_time` is not None
            and datetime.now(UTC) > self.end_time  # type: ignore
        )

    def is_sold(self) -> bool:
        """
        :return: True if the Auction has sold
        """

        if self.status == AuctionStatus.BID_ACCEPTED:
            return True

        return (
            self.status == AuctionStatus.COMMITTED
            # if status is committed, then `end_time` is not None
            and datetime.now(UTC) > self.end_time  # type: ignore
            and self.highest_bid > 0
        )

    def _encode_address(self, hex_encoded_address_bytes: str) -> Address:
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

    def __repr__(self):
        return pformat(
            {
                Auction.status.str_key(): self.status,
                Auction.seller_address.str_key(): self.seller_address,
                Auction.bid_asset_id.str_key(): self.bid_asset_id,
                Auction.min_bid.str_key(): self.min_bid,
                Auction.highest_bidder_address.str_key(): self.highest_bidder_address,
                Auction.highest_bid.str_key(): self.highest_bid,
                Auction.start_time.str_key(): self.start_time.isoformat()
                if self.start_time
                else None,
                Auction.end_time.str_key(): self.end_time.isoformat()
                if self.end_time
                else None,
            }
        )


class _AuctionClient(AppClient):
    def __init__(self, app_client: ApplicationClient):
        if app_client.app_id == 0:
            raise AssertionError("ApplicationClient.app_id must not be 0")

        if not isinstance(app_client.app, Auction):
            raise AssertionError("ApplicationClient.app must be an instance of Auction")

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
        if not self._is_asset_id_valid(asset_id):
            raise InvalidAssetId(asset_id)

    def _is_asset_id_valid(self, asset_id: AssetId) -> bool:
        try:
            self._app_client.client.asset_info(asset_id)
            return True
        except AlgodHTTPError as err:
            print(err)
            if err.code == 404:
                return False
            raise err

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
            self._app_client.client.account_asset_info(self.contract_address, asset_id)[
                "asset-holding"
            ]
        )


class _AuctionClientSupport(AppClient):
    def get_auction_state(self) -> AuctionState:
        """
        :return: AuctionState
        """
        return AuctionState(self.get_application_state())

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
        try:
            bid_asset_holding = self._app_client.client.account_asset_info(
                self.contract_address, bid_asset_id
            )
            return AssetHolding.from_data(bid_asset_holding["asset-holding"])
        except AlgodHTTPError as err:
            if err.code == 404:
                return None
            raise


class AuctionBidder(_AuctionClientSupport):
    """
    Auction client used for placing bids.
    """

    BID_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME, method=get_method_signature(Auction.bid)
    )

    OPTIN_AUCTION_ASSETS_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method="optin_auction_assets",
    )

    def __init__(self, app_client: ApplicationClient):
        if app_client.app_id == 0:
            raise AssertionError("ApplicationClient.app_id must not be 0")

        if not isinstance(app_client.app, Auction):
            raise AssertionError("ApplicationClient.app must be an instance of Auction")

        super().__init__(app_client)

    def bid(self, amount: int) -> ABIResult:
        """
        Used to submit a bid.

        Notes
        -----
        - Auction bidding session must be open
        - The bid must be higher than the current highest bid.
        """
        auction_state = AuctionState(self.get_application_state())
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

        if auction_state.highest_bidder_address:
            highest_bidder = auction_state.highest_bidder_address
            # transaction fees need to cover the inner transaction to refund the highest bidder
            suggested_params.fee = suggested_params.min_fee * 2
        else:
            highest_bidder = Address(ZERO_ADDRESS)

        return self._app_client.call(
            Auction.bid,
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


# TODO: add standardized transaction notes
class AuctionClient(_AuctionClient, _AuctionClientSupport):
    """
    Auction application client
    """

    SET_BID_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(Auction.set_bid_asset),
    )

    OPTIN_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method="optin_asset",
    )

    OPTOUT_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method="optout_asset",
    )

    DEPOSIT_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method="deposit_asset",
    )

    WITHDRAW_ASSET_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(Auction.withdraw_asset),
    )

    COMMIT_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(Auction.commit),
    )

    ACCEPT_BID_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(Auction.accept_bid),
    )

    CANCEL_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(Auction.cancel),
    )

    FINALIZE_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(Auction.finalize),
    )

    LATEST_TIMESTAMP_NOTE: Final[AppTxnNote] = AppTxnNote(
        app=Auction.APP_NAME,
        method=get_method_signature(Auction.latest_timestamp),
    )

    def get_seller_address(self) -> Address:
        """
        Returns auction seller address
        """
        return self.get_auction_state().seller_address

    def set_bid_asset(self, asset_id: AssetId, min_bid: int) -> ABIResult | None:
        """
        Sets or updates the bidd asset settings.

        If the bid asset is already set and if the

        :param asset_id:
        :param min_bid:
        :return: None is returned if there were no changes needed, i.e., no transaction was submitted
        """
        app_state = self.get_auction_state()
        if app_state.bid_asset_id == asset_id and app_state.min_bid == min_bid:
            # then no changes are needed
            return None

        if app_state.seller_address != self._app_client.sender:
            raise AuthError

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
            Auction.set_bid_asset,
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
            Auction.optout_asset,
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
            Auction.optin_asset,
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
        if app_state.seller_address != self._app_client.sender:
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
        if app_state.seller_address != self._app_client.sender:
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
            Auction.withdraw_asset,
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
        if app_state.seller_address != self._app_client.sender:
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
            Auction.commit,
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
            Auction.accept_bid,
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
        if app_state.seller_address != self._app_client.sender:
            raise AuthError

        return self._app_client.call(
            Auction.cancel,
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
                        Auction.finalize,
                        asset=auction_asset.asset_id,
                        close_to=app_state.highest_bidder_address,
                        suggested_params=suggested_params,
                        lease=create_lease(),
                        note=self.FINALIZE_NOTE.encode(),
                    )
                )
            # close out the bid asset to the seller
            results.append(
                self._app_client.call(
                    Auction.finalize,
                    asset=app_state.bid_asset_id,
                    close_to=app_state.seller_address,
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
                        Auction.finalize,
                        asset=auction_asset.asset_id,
                        close_to=app_state.seller_address,
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
                            Auction.finalize,
                            asset=app_state.bid_asset_id,
                            close_to=app_state.seller_address,
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
            Auction.latest_timestamp, note=self.LATEST_TIMESTAMP_NOTE.encode()
        )
        return datetime.fromtimestamp(result.return_value, UTC)
