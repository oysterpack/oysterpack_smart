from dataclasses import dataclass
from datetime import datetime, UTC
from pprint import pformat
from typing import cast, Optional

from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.constants import ZERO_ADDRESS
from algosdk.encoding import encode_address
from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient
from beaker.client import ApplicationClient

from oysterpack.algorand.client.model import Address, AppId, AssetId, AssetHolding
from oysterpack.algorand.client.transactions import create_lease, assets
from oysterpack.algorand.client.transactions.assets import opt_in
from oysterpack.algorand.params import MinimumBalance
from oysterpack.apps.auction_app.contracts.auction import Auction
from oysterpack.apps.auction_app.model.auction import AuctionStatus
from oysterpack.apps.client import AppClient


@dataclass
class InvalidAssetId(Exception):
    asset_id: AssetId


class AuthError(Exception):
    pass


class AuctionState:
    def __init__(self, state: dict[bytes | str, bytes | str | int]):
        self.__state = state

    @property
    def status(self) -> AuctionStatus:
        match self.__state[Auction.status.str_key()]:
            case AuctionStatus.New.value:
                return AuctionStatus.New
            case AuctionStatus.Cancelled.value:
                return AuctionStatus.Cancelled
            case AuctionStatus.Committed.value:
                return AuctionStatus.Committed
            case AuctionStatus.BidAccepted.value:
                return AuctionStatus.BidAccepted
            case AuctionStatus.Finalized.value:
                return AuctionStatus.Finalized
            case _:
                raise ValueError(self.__state[Auction.status.str_key()])

    @property
    def seller_address(self) -> Address:
        return self._encode_address(
            cast(str, self.__state[Auction.seller_address.str_key()])
        )

    @property
    def bid_asset_id(self) -> AssetId | None:
        if Auction.bid_asset_id.str_key() in self.__state.keys():
            return AssetId(cast(int, self.__state[Auction.bid_asset_id.str_key()]))
        return None

    @property
    def min_bid(self) -> int | None:
        if Auction.min_bid.str_key() in self.__state.keys():
            return cast(int, self.__state[Auction.min_bid.str_key()])
        return None

    @property
    def highest_bidder_address(self) -> Address | None:
        if Auction.highest_bidder_address.str_key() in self.__state.keys():
            value = cast(str, self.__state[Auction.highest_bidder_address.str_key()])
            return self._encode_address(value) if value else None
        return None

    @property
    def highest_bid(self) -> int:
        if Auction.highest_bid.str_key() in self.__state.keys():
            return cast(int, self.__state[Auction.highest_bid.str_key()])
        return 0

    @property
    def start_time(self) -> datetime | None:
        if Auction.start_time.str_key() in self.__state.keys():
            value = cast(int, self.__state[Auction.start_time.str_key()])
            return datetime.fromtimestamp(value, UTC) if value else None
        return None

    @property
    def end_time(self) -> datetime | None:
        if Auction.end_time.str_key() in self.__state.keys():
            value = cast(int, self.__state[Auction.end_time.str_key()])
            return datetime.fromtimestamp(value, UTC) if value else None
        return None

    def is_bidding_open(self) -> bool:
        if self.start_time and self.end_time:
            return (
                self.status == AuctionStatus.Committed
                and self.start_time <= datetime.now(UTC) < self.end_time
            )
        return False

    def is_ended(self) -> bool:
        """
        :return: True if the auction has ended, but not yet fully finalized
        """
        if self.status in [
            AuctionStatus.BidAccepted,
            AuctionStatus.Cancelled,
        ]:
            return True

        return (
            self.status == AuctionStatus.Committed
            # if status is committed, then `end_time` is not None
            and datetime.now(UTC) > self.end_time  # type: ignore
        )

    def is_sold(self) -> bool:
        if self.status == AuctionStatus.BidAccepted:
            return True

        return (
            self.status == AuctionStatus.Committed
            # if status is committed, then `end_time` is not None
            and datetime.now(UTC) > self.end_time  # type: ignore
            and self.highest_bid > 0
        )

    def _encode_address(self, hex_encoded_address_bytes: str) -> Address:
        return Address(
            encode_address(
                # seller address is stored as bytes in the contract
                # beaker's ApplicationClient will return the bytes as a hex encoded string
                bytes.fromhex(hex_encoded_address_bytes)
            )
        )

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
    def __init__(
        self,
        app_id: AppId,
        algod_client: AlgodClient,
        signer: TransactionSigner,
        sender: Address | None = None,
    ):
        super().__init__(
            app=Auction(),
            app_id=app_id,
            algod_client=algod_client,
            signer=signer,
            sender=sender,
        )

    def _fund_asset_optin(self):
        """
        Ensures the contract is funded to be able to opt in an asset
        :return:
        """
        account_info = self.get_application_account_info()
        algo_balance = cast(int, account_info["amount"])
        min_balance = cast(int, account_info["min-balance"])
        self.fund(min_balance + MinimumBalance.asset_opt_in - algo_balance)

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
        return AssetHolding.from_data(
            self._app_client.client.account_asset_info(self.contract_address, asset_id)[
                "asset-holding"
            ]
        )


class _AuctionClientSupport(AppClient):
    def get_auction_state(self) -> AuctionState:
        return AuctionState(self.get_application_state())

    def get_auction_assets(self) -> list[AssetHolding]:
        assets = [
            AssetHolding.from_data(asset)
            for asset in self.get_application_account_info()["assets"]
        ]
        bid_asset_id = self.get_auction_state().bid_asset_id
        if bid_asset_id:
            # TODO: adding mypy ignore because mypy is complaining about `asset.asset_id`, even though it is valid
            return [asset for asset in assets if asset.asset_id != bid_asset_id]  # type: ignore
        return assets

    def get_bid_asset_holding(self) -> AssetHolding:
        bid_asset_id = self.get_auction_state().bid_asset_id
        bid_asset_holding = self._app_client.client.account_asset_info(
            self.contract_address, bid_asset_id
        )
        return AssetHolding.from_data(bid_asset_holding["asset-holding"])


# TODO: add standardized transaction notes
class AuctionBidder(_AuctionClientSupport):
    def __init__(
        self,
        app_id: AppId,
        algod_client: AlgodClient,
        signer: TransactionSigner,
        sender: Address | None = None,
    ):
        super().__init__(
            app=Auction(),
            app_id=app_id,
            algod_client=algod_client,
            signer=signer,
            sender=sender,
        )

    @classmethod
    def from_client(cls, app_client: ApplicationClient) -> "AuctionBidder":
        return cls(
            AppId(app_client.app_id),
            app_client.client,
            cast(TransactionSigner, app_client.signer),
            cast(Optional[Address], app_client.sender),
        )

    def bid(self, amount: int):
        auction_state = AuctionState(self.get_application_state())
        if not auction_state.is_bidding_open():
            raise AssertionError("auction is not open for bidding")

        if amount <= auction_state.highest_bid:
            raise AssertionError(
                f"bid is too low - current highest bid is: {auction_state.highest_bid}"
            )

        asset_transfer_txn = assets.transfer(
            sender=cast(Address, self._app_client.sender),
            receiver=self.contract_address,
            asset_id=cast(AssetId, auction_state.bid_asset_id),
            amount=amount,
            suggested_params=self.suggested_params(),
        )

        sp = self.suggested_params()

        if auction_state.highest_bidder_address:
            highest_bidder = auction_state.highest_bidder_address
            # transaction fees need to cover the inner transaction to refund the highest bidder
            sp.fee = sp.min_fee * 2
        else:
            highest_bidder = Address(ZERO_ADDRESS)

        self._app_client.call(
            Auction.bid,
            bid=TransactionWithSigner(
                asset_transfer_txn,
                cast(TransactionSigner, self._app_client.signer),
            ),
            highest_bidder=highest_bidder,
            bid_asset=auction_state.bid_asset_id,
            sender=self._app_client.sender,
            suggested_params=sp,
        )

    def optin_auction_assets(self):
        bidder = self._app_client.sender
        for asset in self.get_auction_assets():
            try:
                self._app_client.client.account_asset_info(bidder, asset.asset_id)
            except AlgodHTTPError as err:
                if err.code == 404:  # bidder account is not opted in
                    txn = opt_in(
                        account=bidder,
                        asset_id=asset.asset_id,
                        suggested_params=self.suggested_params(),
                    )
                    atc = AtomicTransactionComposer()
                    atc.add_transaction(
                        TransactionWithSigner(txn, self._app_client.signer)
                    )
                    atc.execute(self._app_client.client, 4)
                else:
                    raise


# TODO: add standardized transaction notes
class AuctionClient(_AuctionClient, _AuctionClientSupport):
    @classmethod
    def from_client(cls, app_client: ApplicationClient) -> "AuctionClient":
        return cls(
            AppId(app_client.app_id),
            app_client.client,
            cast(TransactionSigner, app_client.signer),
            cast(Optional[Address], app_client.sender),
        )

    def get_seller_address(self) -> Address:
        return self.get_auction_state().seller_address

    def set_bid_asset(self, asset_id: AssetId, min_bid: int):
        """
        Sets or updates the bidd asset settings.

        If the bid asset is already set and if the

        :param asset_id:
        :param min_bid:
        :return:
        """
        app_state = self.get_auction_state()
        if app_state.bid_asset_id == asset_id and app_state.min_bid == min_bid:
            # then no changes are needed
            return

        if app_state.seller_address != self._app_client.sender:
            raise AuthError

        # if the bid asset is being updated, then opt out the bid asset
        if app_state.bid_asset_id and app_state.bid_asset_id != asset_id:
            self.optout_asset(app_state.bid_asset_id)

        # transaction fees need to cover the inner transaction to opt in the bid asset
        sp = self.suggested_params(txn_count=2)

        # if only the min bid is being changed, then no bid asset opt in is needed
        if app_state.bid_asset_id and app_state.bid_asset_id == asset_id:
            sp.fee = sp.min_fee
        else:
            self._fund_asset_optin()

        self._app_client.call(
            Auction.set_bid_asset,
            bid_asset=asset_id,
            min_bid=min_bid,
            suggested_params=sp,
            lease=create_lease(),
        )

    def optout_asset(self, asset_id: AssetId):
        """
        If the contract does not hold the asset, then this is a noop.

        Asserts
        -------
        1. sender is seller

        :param asset_id:
        :return:
        """

        if not self._is_asset_opted_in(asset_id):
            return

        if self.get_seller_address() != self._app_client.sender:
            raise AuthError

        self._app_client.call(
            Auction.optout_asset,
            asset=asset_id,
            suggested_params=self.suggested_params(txn_count=2),
            lease=create_lease(),
        )

    def optin_asset(self, asset_id: AssetId):
        """
        If the asset is not already opted in, then opt in the asset.
        Also makes sure the Auction contract is funded to opt in the asset.
        """

        if self.get_seller_address() != self._app_client.sender:
            raise AuthError

        self._assert_valid_asset_id(asset_id)
        if not self._is_asset_opted_in(asset_id):
            self._fund_asset_optin()

            self._app_client.call(
                Auction.optin_asset,
                asset=asset_id,
                suggested_params=self.suggested_params(txn_count=2),
                lease=create_lease(),
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
        if app_state.status != AuctionStatus.New:
            raise AssertionError(
                "asset deposit is only allowed when auction status is 'New'"
            )

        if app_state.bid_asset_id == asset_id:
            raise AssertionError("asset deposits are not allowed for the bid asset")

        # ensure the auction has opted in the asset
        self.optin_asset(asset_id)

        # transfer the asset
        # the transfer will fail if there are insufficient funds
        asset_transfer_txn = assets.transfer(
            sender=Address(cast(str, self._app_client.sender)),
            receiver=self.contract_address,
            asset_id=asset_id,
            amount=amount,
            suggested_params=self.suggested_params(),
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

        if app_state.status != AuctionStatus.New:
            raise AssertionError(
                "asset withdrawal is only allowed when auction status is 'New'"
            )

        self._app_client.call(
            Auction.withdraw_asset,
            asset=asset_id,
            amount=amount,
            suggested_params=self.suggested_params(txn_count=2),
        )

        return self._get_asset_holding(asset_id)

    def commit(self, start_time: datetime | None, end_time: datetime):
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

        if app_state.status != AuctionStatus.New:
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

        self._app_client.call(
            Auction.commit,
            start_time=int(start_time.timestamp()),
            end_time=int(end_time.timestamp()),
        )

    def accept_bid(self):
        app_state = self.get_auction_state()
        if app_state.status != AuctionStatus.Committed:
            raise AssertionError("auction status must be `Committed`")
        if app_state.highest_bid == 0:
            raise AssertionError("auction has no bid")
        if datetime.now(UTC) > app_state.end_time:
            raise AssertionError("auction has ended")

        self._app_client.call(Auction.accept_bid)

    def cancel(self):
        app_state = self.get_auction_state()
        if app_state.status != AuctionStatus.New:
            raise AssertionError(
                "auction can only be commited when auction status is 'New'"
            )
        if app_state.seller_address != self._app_client.sender:
            raise AuthError

        self._app_client.call(Auction.cancel)

    def finalize(self):
        app_state = self.get_auction_state()
        if app_state.status == AuctionStatus.Finalized:
            return
        if not app_state.is_ended():
            raise AssertionError("auction cannot be finalized because it has not ended")

        sp = self.suggested_params(txn_count=2)
        if app_state.is_sold():
            # close out auction assets to the highest bidder
            for asset in self.get_auction_assets():
                self._app_client.call(
                    Auction.finalize,
                    asset=asset.asset_id,
                    close_to=app_state.highest_bidder_address,
                    suggested_params=sp,
                    lease=create_lease(),
                )
            # close out the bid asset to the seller
            self._app_client.call(
                Auction.finalize,
                asset=app_state.bid_asset_id,
                close_to=app_state.seller_address,
                suggested_params=sp,
                lease=create_lease(),
            )
        else:
            # close out auction assets to the seller
            for asset in self.get_auction_assets():
                self._app_client.call(
                    Auction.finalize,
                    asset=asset.asset_id,
                    close_to=app_state.seller_address,
                    suggested_params=sp,
                    lease=create_lease(),
                )
            if app_state.bid_asset_id:
                try:
                    self.get_bid_asset_holding()
                    self._app_client.call(
                        Auction.finalize,
                        asset=app_state.bid_asset_id,
                        close_to=app_state.seller_address,
                        suggested_params=sp,
                        lease=create_lease(),
                    )
                except AlgodHTTPError as err:
                    if err.code != 404:
                        raise

    def latest_timestamp(self) -> datetime:
        result = self._app_client.call(Auction.latest_timestamp)
        return datetime.fromtimestamp(result.return_value, UTC)
