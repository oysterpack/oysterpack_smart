from dataclasses import dataclass
from datetime import datetime, UTC
from pprint import pformat
from typing import cast, Optional

from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    AtomicTransactionComposer,
)
from algosdk.encoding import encode_address
from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient
from beaker.client import ApplicationClient

from oysterpack.algorand.client.model import Address, AppId, AssetId, AssetHolding
from oysterpack.algorand.client.transactions import create_lease, assets
from oysterpack.algorand.params import MinimumBalance
from oysterpack.apps.auction_app.contracts.auction import Auction
from oysterpack.apps.auction_app.model.auction import AuctionStatus
from oysterpack.apps.client import AppClient


@dataclass
class InvalidAssetId(Exception):
    asset_id: AssetId


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
            case AuctionStatus.Started.value:
                return AuctionStatus.Started
            case AuctionStatus.Sold.value:
                return AuctionStatus.Sold
            case AuctionStatus.NotSold.value:
                return AuctionStatus.NotSold
            case AuctionStatus.Finalized.value:
                return AuctionStatus.Finalized
            case _:
                raise ValueError(self.__state[Auction.status.str_key()])

    @property
    def seller_address(self) -> Address:
        return Address(
            encode_address(
                bytes.fromhex(cast(str, self.__state[Auction.seller_address.str_key()]))
            )
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
            return Address(value) if value else None
        return None

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

    def __repr__(self):
        return pformat(
            {
                Auction.status.str_key(): self.status,
                Auction.seller_address.str_key(): self.seller_address,
                Auction.bid_asset_id.str_key(): self.bid_asset_id,
                Auction.min_bid.str_key(): self.min_bid,
                Auction.highest_bidder_address.str_key(): self.highest_bidder_address,
                Auction.start_time.str_key(): self.start_time,
                Auction.end_time.str_key(): self.end_time,
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


class AuctionClient(_AuctionClient):
    @classmethod
    def from_client(cls, app_client: ApplicationClient) -> "AuctionClient":
        return cls(
            AppId(app_client.app_id),
            app_client.client,
            cast(TransactionSigner, app_client.signer),
            cast(Optional[Address], app_client.sender),
        )

    def get_auction_state(self) -> AuctionState:
        return AuctionState(self.get_application_state())

    def get_seller_address(self) -> Address:
        app_state = self.get_application_state()
        # seller address is stored as bytes in the contract
        # beaker's ApplicationClient will return the bytes as a hex encoded string
        return Address(
            encode_address(
                bytes.fromhex(cast(str, app_state[Auction.seller_address.str_key()]))
            )
        )

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

        # if the bid asset is being updated, then opt out the bid asset
        if app_state.bid_asset_id and app_state.bid_asset_id != asset_id:
            self.optout_asset(app_state.bid_asset_id)

        sp = self._app_client.client.suggested_params()
        # transaction fees need to cover the inner transaction to opt in the bid asset
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True

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
        sp = self._app_client.client.suggested_params()
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True
        self._app_client.call(
            Auction.optout_asset,
            asset=asset_id,
            suggested_params=sp,
            lease=create_lease(),
        )

    def optin_asset(self, asset_id: AssetId):
        """
        If the asset is not already opted in, then opt in the asset.
        Also makes sure the Auction contract is funded to opt in the asset.
        """

        self._assert_valid_asset_id(asset_id)
        if not self._is_asset_opted_in(asset_id):
            self._fund_asset_optin()

            sp = self._app_client.client.suggested_params()
            sp.fee = sp.min_fee * 2
            sp.flat_fee = True

            self._app_client.call(
                Auction.optin_asset,
                asset=asset_id,
                suggested_params=sp,
                lease=create_lease(),
            )

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

    def deposit_asset(self, asset_id: AssetId, amount: int) -> AssetHolding:
        """
        If necessary, the asset is opted in and the contract is funded.

        Asserts
        -------
        1. amount > 0
        2. auction status == New
        3. asset_id != bid_asset_id

        :param asset_id: bid asset deposits are not allowed
        :param amount: must be > 0
        """

        # check args
        if amount <= 0:
            raise AssertionError("amount must be > 0")

        app_state = self.get_auction_state()
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
            suggested_params=self._app_client.client.suggested_params,
        )
        atc = AtomicTransactionComposer()
        self._app_client.add_transaction(atc, asset_transfer_txn)
        atc.execute(self._app_client.client, 4)

        return AssetHolding.from_data(
            self._app_client.client.account_asset_info(self.contract_address, asset_id)[
                "asset-holding"
            ]
        )
