from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from enum import auto
from typing import Optional

from sqlalchemy import Select, select, func

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.commands.data.SqlAlchemySupport import (
    SqlAlchemySupport,
)
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data.auction import TAuction, TAuctionAsset
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.core.command import Command


class AuctionSortField(IntEnum):
    AuctionId = auto()

    Status = auto()
    Seller = auto()

    BidAsset = auto()
    MinBid = auto()
    HighestBid = auto()

    StartTime = auto()
    EndTime = auto()

    AuctionAsset = auto()
    AuctionAssetAmount = auto()


@dataclass(slots=True)
class AuctionSort:
    """
    Auction.app_id is always append to the sort field.
    """

    field: AuctionSortField
    asc: bool = True  # sort order, i.e., ascending or descending


@dataclass(slots=True)
class AuctionSearchFilters:
    """
    Auction search filters
    """

    app_id: set[AppId] = field(default_factory=set)

    status: set[AuctionStatus] = field(default_factory=set)
    seller: set[Address] = field(default_factory=set)

    bid_asset_id: set[AssetId] = field(default_factory=set)
    min_bid: int | None = None  # min_bid >= Auction.min_bid

    highest_bidder: set[Address] = field(default_factory=set)
    highest_bid: int | None = None  # highest_bid >= Auction.highest_bid

    start_time: datetime | None = None  # start_time >= Auction.start_time
    end_time: datetime | None = None  # end_time >= Auction.end_time

    assets: set[AssetId] = field(default_factory=set)
    asset_amounts: dict[AssetId, int] = field(default_factory=dict)


@dataclass(slots=True)
class AuctionSearchResult:
    """
    Auction search result
    """

    auctions: list[Auction]

    total_count: int


@dataclass(slots=True)
class AuctionSearchRequest:
    """
    Auction search request
    """

    filters: AuctionSearchFilters | None = None

    sort: AuctionSort | None = None

    # used for paging
    limit: int = 100
    offset: int = 0

    def next_page(
        self, search_result: AuctionSearchResult
    ) -> Optional["AuctionSearchRequest"]:
        """
        :return: None if there are no more results to retrieve
        """
        if search_result.total_count == 0:
            return None

        offset = self.offset + self.limit
        if offset >= search_result.total_count:
            return None
        return AuctionSearchRequest(
            filters=self.filters,
            sort=self.sort,
            limit=self.limit,
            offset=offset,
        )

    def previous_page(
        self, search_result: AuctionSearchResult
    ) -> Optional["AuctionSearchRequest"]:
        """
        :return: None if there are no more results to retrieve
        """
        if search_result.total_count == 0:
            return None

        if self.offset == 0:
            # we are at the first page
            return None

        offset = self.offset - self.limit
        if offset < 0:
            offset = 0

        return AuctionSearchRequest(
            filters=self.filters,
            sort=self.sort,
            limit=self.limit,
            offset=offset,
        )

    def goto(
        self, search_result: AuctionSearchResult, offset: int, limit: int | None = None
    ) -> Optional["AuctionSearchRequest"]:
        if offset < 0:
            raise AssertionError("offset must be >= 0")

        if offset >= search_result.total_count:
            raise AssertionError(f"offset must be < {search_result.total_count}")

        return AuctionSearchRequest(
            filters=self.filters,
            sort=self.sort,
            limit=self.limit if limit is None else limit,
            offset=offset,
        )


class SearchAuctions(
    Command[AuctionSearchRequest, AuctionSearchResult],
    SqlAlchemySupport,
):
    def __call__(self, request: AuctionSearchRequest) -> AuctionSearchResult:
        logger = super().get_logger()

        def build_where_clause(select: Select) -> Select:
            if request.filters is None:
                return select

            if len(request.filters.app_id) > 0:
                select = select.where(TAuction.app_id.in_(request.filters.app_id))

            if len(request.filters.status) > 0:
                select = select.where(TAuction.status.in_(request.filters.status))

            if len(request.filters.seller) > 0:
                select = select.where(TAuction.seller.in_(request.filters.seller))

            if len(request.filters.bid_asset_id) > 0:
                select = select.where(
                    TAuction.bid_asset_id.in_(request.filters.bid_asset_id)
                )

            if request.filters.min_bid and request.filters.min_bid > 0:
                select = select.where(TAuction.min_bid >= request.filters.min_bid)

            if len(request.filters.highest_bidder) > 0:
                select = select.where(
                    TAuction.highest_bidder.in_(request.filters.highest_bidder)
                )

            if request.filters.highest_bid and request.filters.highest_bid > 0:
                select = select.where(
                    TAuction.highest_bid >= request.filters.highest_bid
                )

            return select

        def add_sort(select: Select) -> Select:
            if request.sort is None:
                return select.order_by(TAuction.app_id)

            match request.sort.field:
                case AuctionSortField.AuctionId:
                    if request.sort.asc:
                        return select.order_by(TAuction.app_id)
                    else:
                        return select.order_by(TAuction.app_id.desc())
                case AuctionSortField.Status:
                    if request.sort.asc:
                        return select.order_by(TAuction.status)
                    else:
                        return select.order_by(TAuction.status.desc())
                case AuctionSortField.Seller:
                    if request.sort.asc:
                        return select.order_by(TAuction.seller)
                    else:
                        return select.order_by(TAuction.seller.desc())
                case AuctionSortField.BidAsset:
                    if request.sort.asc:
                        return select.order_by(TAuction.bid_asset_id.nullslast())
                    else:
                        return select.order_by(TAuction.bid_asset_id.desc().nullslast())
                case AuctionSortField.MinBid:
                    if request.sort.asc:
                        return select.order_by(TAuction.min_bid.nullslast())
                    else:
                        return select.order_by(TAuction.min_bid.desc().nullslast())
                case AuctionSortField.HighestBid:
                    if request.sort.asc:
                        return select.order_by(TAuction.highest_bid.nullslast())
                    else:
                        return select.order_by(TAuction.highest_bid.desc().nullslast())
                case AuctionSortField.StartTime:
                    if request.sort.asc:
                        return select.order_by(TAuction.start_time.nullslast())
                    else:
                        return select.order_by(TAuction.start_time.desc().nullslast())
                case AuctionSortField.EndTime:
                    if request.sort.asc:
                        return select.order_by(TAuction.end_time.nullslast())
                    else:
                        return select.order_by(TAuction.end_time.desc().nullslast())
                case AuctionSortField.AuctionAsset:
                    if request.sort.asc:
                        return select.order_by(TAuctionAsset.asset_id.nullslast())
                    else:
                        return select.order_by(
                            TAuctionAsset.asset_id.desc().nullslast()
                        )
                case AuctionSortField.AuctionAssetAmount:
                    if request.sort.asc:
                        return select.order_by(TAuctionAsset.amount.nullslast())
                    else:
                        return select.order_by(TAuctionAsset.amount.desc().nullslast())
                case other:
                    raise AssertionError(
                        f"AuctionSortField match case is missing: {other}"
                    )

        count_query = build_where_clause(
            # pylint: disable=not-callable
            select(func.count(TAuction.app_id.distinct())).outerjoin(TAuction.assets)
        )

        logger.debug(f"count_query: {count_query}")

        query = build_where_clause(select(TAuction).outerjoin(TAuction.assets))
        query = add_sort(query)
        query = query.limit(request.limit)
        query = query.offset(request.offset)
        # effectively dedupes the search results across the outer join
        query = query.group_by(TAuction.app_id)

        logger.debug(f"query: {query}")

        with self.session_factory() as session:
            return AuctionSearchResult(
                total_count=session.scalar(count_query),
                auctions=[auction.to_auction() for auction in session.scalars(query)],
            )
