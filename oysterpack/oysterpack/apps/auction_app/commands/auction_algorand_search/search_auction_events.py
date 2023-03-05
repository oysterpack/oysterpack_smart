"""
Searches for Auction Algorand transactions
"""
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import Any

from algosdk.v2client.indexer import IndexerClient

from oysterpack.algorand.client.model import TxnId, AppId
from oysterpack.algorand.client.transactions.note import AppTxnNote
from oysterpack.apps.auction_app.client.auction_client import (
    AuctionClient,
    AuctionBidder,
)


class AuctionEvent(IntEnum):
    """
    Auction Events
    """

    # 0-1 auction lifecycle events
    COMMITTED = auto()

    # 0-N auction lifecycle events
    BID = auto()
    # 0-1 auction lifecycle events
    BID_ACCEPTED = auto()

    # 0-1 auction lifecycle events
    FINALIZED = auto()
    # 0-1 auction lifecycle events
    CANCELLED = auto()


@dataclass(slots=True)
class SearchAuctionEventsRequest:
    """
    SearchAuctionTransactionsRequest
    """

    auction_app_id: AppId
    event: AuctionEvent

    limit: int = 100
    next_token: str | None = None


@dataclass(slots=True)
class SearchAuctionEventsResult:
    """
    SearchAuctionTransactionsResult
    """

    event: AuctionEvent
    txn_ids: list[TxnId]

    # used for paging
    next_token: str | None


class SearchAuctionEvents:
    """
    Used to search Algorand transactions for Auction events
    """

    def __init__(self, indexer: IndexerClient):
        self._indexer = indexer

    def __call__(
        self,
        request: SearchAuctionEventsRequest,
    ) -> SearchAuctionEventsResult:
        result = self.__search_transactions(request)
        return SearchAuctionEventsResult(
            event=request.event,
            txn_ids=[txn["id"] for txn in result["transactions"]],
            next_token=result["next-token"],
        )

    def __search_transactions(
        self, request: SearchAuctionEventsRequest
    ) -> dict[str, Any]:
        return self._indexer.search_transactions(
            application_id=request.auction_app_id,
            note_prefix=self.__txn_note_prefix(request.event).encode(),
            limit=request.limit,
            next_page=request.next_token,
        )

    def __txn_note_prefix(self, event: AuctionEvent) -> AppTxnNote:
        match event:
            case AuctionEvent.COMMITTED:
                return AuctionClient.COMMIT_NOTE
            case AuctionEvent.BID:
                return AuctionBidder.BID_NOTE
            case AuctionEvent.BID_ACCEPTED:
                return AuctionClient.ACCEPT_BID_NOTE
            case AuctionEvent.FINALIZED:
                return AuctionClient.FINALIZE_NOTE
            case AuctionEvent.CANCELLED:
                return AuctionClient.CANCEL_NOTE
            case _:
                raise AssertionError(f"event not supported: {event}")
