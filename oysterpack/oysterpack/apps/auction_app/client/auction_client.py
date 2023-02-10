from datetime import datetime, UTC
from pprint import pformat
from typing import cast, Optional, Any

from algosdk.atomic_transaction_composer import TransactionSigner
from algosdk.encoding import encode_address
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from beaker.client import ApplicationClient

from oysterpack.algorand.client.model import Address, AppId, AssetId
from oysterpack.algorand.client.transactions import create_lease
from oysterpack.apps.auction_app.contracts.auction import Auction
from oysterpack.apps.auction_app.model.auction import AuctionStatus


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


class AuctionClient:
    def __init__(
        self,
        app_id: AppId,
        algod_client: AlgodClient,
        signer: TransactionSigner,
        sender: Address | None = None,
    ):
        self._app_client = ApplicationClient(
            app=Auction(),
            app_id=app_id,
            client=algod_client,
            signer=signer,
            sender=sender,
        )

    @classmethod
    def from_client(cls, app_client: ApplicationClient) -> "AuctionClient":
        return cls(
            AppId(app_client.app_id),
            app_client.client,
            cast(TransactionSigner, app_client.signer),
            cast(Optional[Address], app_client.sender),
        )

    @property
    def contract_address(self) -> Address:
        return Address(get_application_address(self._app_client.app_id))

    @property
    def app_id(self) -> AppId:
        return AppId(self._app_client.app_id)

    def get_seller_address(self) -> Address:
        app_state = self._app_client.get_application_state()
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
        app_state = self.get_application_state()
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

    def fund(self, algo_amount: int):
        self._app_client.fund(algo_amount)

    def get_application_account_info(self) -> dict[str, Any]:
        return self._app_client.get_application_account_info()

    def get_application_state(self) -> AuctionState:
        return AuctionState(self._app_client.get_application_state())
