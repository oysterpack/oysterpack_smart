"""
Searches for Auction Algorand transactions
"""
from base64 import b64decode
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import Any

from algosdk.v2client.indexer import IndexerClient

from oysterpack.algorand.client.model import AppId, Transaction
from oysterpack.apps.auction_app.client.auction_client import (
    AuctionClient,
    AuctionBidder,
    AuctionPhase,
)
from oysterpack.apps.auction_app.contracts import auction
from oysterpack.apps.auction_app.domain.auction import AuctionAppId


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
    # either a specific event or set of events that are part of the specified phase
    filter: AuctionEvent | AuctionPhase

    min_round: int | None = None
    limit: int = 100
    next_token: str | None = None


@dataclass(slots=True)
class SearchAuctionEventsResult:
    """
    SearchAuctionTransactionsResult
    """

    filter: AuctionEvent | AuctionPhase

    # multiple transactions may ahve occured per Auction
    # the transaction note can be inspected to determine which contract method was invoked
    txns: dict[AuctionAppId, list[Transaction]] | None = None

    # used for paging
    next_token: str | None = None

    @property
    def max_confirmed_round(self) -> int | None:
        """
        :return: max confirmed round for the list of txns or None if the search resulted in no matching transactions
        """
        if self.txns is None or len(self.txns) == 0:
            return None

        max_round = 0
        for txns in self.txns.values():
            txns_max_round = max(txn.confirmed_round for txn in txns)
            if txns_max_round > max_round:
                max_round = txns_max_round

        return max_round


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

        if len(result["transactions"]) == 0:
            return SearchAuctionEventsResult(filter=request.filter)

        txns: dict[AuctionAppId, list[Transaction]] = {}
        for txn in result["transactions"]:
            app_id = AuctionAppId(txn["application-transaction"]["application-id"])
            transaction = Transaction(
                txn["id"], txn["confirmed-round"], b64decode(txn["note"]).decode()
            )
            if app_id in txns:
                txns[app_id].append(transaction)
            else:
                txns[app_id] = [transaction]
        return SearchAuctionEventsResult(
            filter=request.filter,
            txns=txns,
            next_token=result["next-token"] if "next-token" in result else None,
        )

    def __search_transactions(
        self, request: SearchAuctionEventsRequest
    ) -> dict[str, Any]:
        return self._indexer.search_transactions(
            application_id=request.auction_app_id,
            note_prefix=self.__txn_note_prefix(request.filter),
            min_round=request.min_round,
            limit=request.limit,
            next_page=request.next_token,
        )

    def __txn_note_prefix(self, filter: AuctionEvent | AuctionPhase) -> bytes:
        if isinstance(filter, AuctionEvent):
            match filter:
                case AuctionEvent.COMMITTED:
                    return AuctionClient.COMMIT_NOTE.encode()
                case AuctionEvent.BID:
                    return AuctionBidder.BID_NOTE.encode()
                case AuctionEvent.BID_ACCEPTED:
                    return AuctionClient.ACCEPT_BID_NOTE.encode()
                case AuctionEvent.FINALIZED:
                    return AuctionClient.FINALIZE_NOTE.encode()
                case AuctionEvent.CANCELLED:
                    return AuctionClient.CANCEL_NOTE.encode()
                case _:
                    raise AssertionError(f"event not supported: {filter}")
        elif isinstance(filter, AuctionPhase):
            return f"{auction.APP_NAME}/{filter}".encode()
