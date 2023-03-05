"""
Searches for Auction Algorand transactions
"""
import base64
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import Any

from algosdk.abi.uint_type import UintType
from algosdk.v2client.indexer import IndexerClient

from oysterpack.algorand.client.model import AppId, TxnId
from oysterpack.algorand.client.transactions.note import AppTxnNote
from oysterpack.apps.auction_app.client.auction_manager_client import (
    AuctionManagerClient,
)
from oysterpack.apps.auction_app.domain.auction import AuctionAppId


class AuctionManagerEvent(IntEnum):
    """
    AuctionManager Events
    """

    AUCTION_CREATED = auto()
    AUCTION_DELETED = auto()


@dataclass(slots=True)
class SearchAuctionManagerEventsRequest:
    """
    SearchAuctionManagerEventsRequest
    """

    auction_manager_app_id: AppId
    event: AuctionManagerEvent

    min_round: int | None = None
    limit: int = 100
    next_token: str | None = None


@dataclass(slots=True)
class Transaction:
    id: TxnId
    confirmed_round: int


@dataclass(slots=True)
class SearchAuctionManagerEventsResult:
    """
    SearchAuctionManagerEventsResult
    """

    event: AuctionManagerEvent

    auction_txns: dict[AuctionAppId, Transaction] | None = None

    # used for paging
    next_token: str | None = None


class SearchAuctionManagerEvents:
    """
    Used to search Algorand transactions for AuctionManager events
    """

    def __init__(self, indexer: IndexerClient):
        self._indexer = indexer

    def __call__(
        self, request: SearchAuctionManagerEventsRequest
    ) -> SearchAuctionManagerEventsResult:
        result = self.__search_transactions(request)
        if len(result["transactions"]) == 0:
            return SearchAuctionManagerEventsResult(event=request.event)

        return SearchAuctionManagerEventsResult(
            event=request.event,
            auction_txns={
                self._auction_app_id(request.event, txn): Transaction(
                    txn["id"], txn["confirmed-round"]
                )
                for txn in result["transactions"]
            },
            next_token=result["next-token"],
        )

    def __search_transactions(
        self, request: SearchAuctionManagerEventsRequest
    ) -> dict[str, Any]:
        return self._indexer.search_transactions(
            application_id=request.auction_manager_app_id,
            note_prefix=self._txn_note_prefix(request.event).encode(),
            limit=request.limit,
            min_round=request.min_round,
            next_page=request.next_token,
        )

    def _auction_app_id(
        self, event: AuctionManagerEvent, txn: dict[str, Any]
    ) -> AuctionAppId:
        match event:
            case AuctionManagerEvent.AUCTION_CREATED:
                return AuctionAppId(
                    # app ID txn log encoding: first 4 bytes are the return prefix, next 8 are uint64 bytes
                    AppId(UintType(64).decode(base64.b64decode(txn["logs"][0])[4:]))
                )
            case AuctionManagerEvent.AUCTION_DELETED:
                return AuctionAppId(txn["application-transaction"]["foreign-apps"][0])
            case _:
                raise AssertionError(f"event not supported: {event}")

    def _txn_note_prefix(self, event: AuctionManagerEvent) -> AppTxnNote:
        match event:
            case AuctionManagerEvent.AUCTION_CREATED:
                return AuctionManagerClient.CREATE_AUCTION_NOTE
            case AuctionManagerEvent.AUCTION_DELETED:
                return AuctionManagerClient.DELETE_FINALIZED_AUCTION_NOTE
            case _:
                raise AssertionError(f"event not supported: {event}")
