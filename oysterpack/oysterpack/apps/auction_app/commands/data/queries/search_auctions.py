"""
Command for auction database search
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from enum import auto
from typing import Optional

from sqlalchemy import Select, select, func, and_, or_, false

from oysterpack.algorand.client.model import AppId, Address, AssetId
from oysterpack.apps.auction_app.commands.data import (
    SqlAlchemySupport,
)
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from oysterpack.apps.auction_app.data.auction import TAuction, TAuctionAsset
from oysterpack.apps.auction_app.domain.auction import Auction
from oysterpack.core.command import Command


class AuctionSortField(IntEnum):
    """
    Auction query sort fields
    """

    AUCTION_ID = auto()

    STATUS = auto()
    SELLER = auto()

    BID_ASSET = auto()
    MIN_BID = auto()
    HIGHEST_BID = auto()

    START_TIME = auto()
    END_TIME = auto()

    AUCTION_ASSET = auto()
    AUCTION_ASSET_AMOUNT = auto()


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

    # pylint: disable=too-many-instance-attributes

    app_id: set[AppId] = field(default_factory=set)
    auction_manager_app_id: set[AppId] = field(default_factory=set)

    status: set[AuctionStatus] = field(default_factory=set)
    seller: set[Address] = field(default_factory=set)

    bid_asset_id: set[AssetId] = field(default_factory=set)
    min_bid: int | None = None  # min_bid >= Auction.min_bid

    highest_bidder: set[Address] = field(default_factory=set)
    # where the min bid is at least the specified amount
    highest_bid: int | None = None  # highest_bid >= Auction.highest_bid

    start_time: datetime | None = None  # start_time >= Auction.start_time
    end_time: datetime | None = None  # end_time >= Auction.end_time

    assets: set[AssetId] = field(default_factory=set)
    # where asset amount is at least the specified amount
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

    # if None, then the default sort is set to TAuction.app_id asc
    sort: AuctionSort = field(
        default_factory=lambda: AuctionSort(AuctionSortField.AUCTION_ID)
    )

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

        offset = max(self.offset - self.limit, 0)

        return AuctionSearchRequest(
            filters=self.filters,
            sort=self.sort,
            limit=self.limit,
            offset=offset,
        )

    def goto(
        self,
        search_result: AuctionSearchResult,
        offset: int,
        limit: int | None = None,
    ) -> Optional["AuctionSearchRequest"]:
        """
        Used to construct a search request for search results starting at the specified offset.
        """

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
    """
    SearchAuctions
    """

    def __call__(self, request: AuctionSearchRequest) -> AuctionSearchResult:
        # pylint: disable=too-many-statements

        logger = super().get_logger()

        def build_where_clause(select_clause: Select) -> Select:
            # pylint: disable=too-many-branches

            if request.filters is None:
                return select_clause

            if len(request.filters.app_id) > 0:
                select_clause = select_clause.where(
                    TAuction.app_id.in_(request.filters.app_id)
                )

            if len(request.filters.auction_manager_app_id) > 0:
                select_clause = select_clause.where(
                    TAuction.auction_manager_app_id.in_(
                        request.filters.auction_manager_app_id
                    )
                )

            if len(request.filters.status) > 0:
                select_clause = select_clause.where(
                    TAuction.status.in_(request.filters.status)
                )

            if len(request.filters.seller) > 0:
                select_clause = select_clause.where(
                    TAuction.seller.in_(request.filters.seller)
                )

            if len(request.filters.bid_asset_id) > 0:
                select_clause = select_clause.where(
                    TAuction.bid_asset_id.in_(request.filters.bid_asset_id)
                )

            if request.filters.min_bid and request.filters.min_bid > 0:
                select_clause = select_clause.where(
                    TAuction.min_bid >= request.filters.min_bid
                )

            if len(request.filters.highest_bidder) > 0:
                select_clause = select_clause.where(
                    TAuction.highest_bidder.in_(request.filters.highest_bidder)
                )

            if request.filters.highest_bid and request.filters.highest_bid > 0:
                select_clause = select_clause.where(
                    TAuction.highest_bid >= request.filters.highest_bid
                )

            if request.filters.start_time:
                select_clause = select_clause.where(
                    TAuction.start_time >= int(request.filters.start_time.timestamp())
                )

            if request.filters.end_time:
                select_clause = select_clause.where(
                    TAuction.end_time <= int(request.filters.end_time.timestamp())
                )

            # dedupe auction asset filters
            # If an asset is specified in `asset_amounts`, then remove the asset from the`assets` filter
            assets = request.filters.assets - request.filters.asset_amounts.keys()
            for asset_id, amount in list(request.filters.asset_amounts.items()):
                if amount <= 0:
                    assets.add(asset_id)
                    del request.filters.asset_amounts[asset_id]

            asset_amount_filter_expressions = [
                and_(
                    TAuctionAsset.asset_id == asset_id,
                    TAuctionAsset.amount >= amount,
                )
                for asset_id, amount in request.filters.asset_amounts.items()
            ]

            if len(assets) > 0 and len(request.filters.asset_amounts) == 0:
                select_clause = select_clause.where(TAuctionAsset.asset_id.in_(assets))
            elif len(request.filters.asset_amounts) > 0 and len(assets) == 0:
                select_clause = select_clause.where(
                    or_(false(), *asset_amount_filter_expressions)
                )
            elif len(request.filters.asset_amounts) > 0 and len(assets) > 0:
                select_clause = select_clause.where(
                    or_(
                        TAuctionAsset.asset_id.in_(assets),
                        *asset_amount_filter_expressions,
                    )
                )

            return select_clause

        def add_sort(select_clause: Select) -> Select:
            # pylint: disable=too-many-return-statements

            match request.sort.field:
                case AuctionSortField.AUCTION_ID:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.app_id)
                    return select_clause.order_by(TAuction.app_id.desc())
                case AuctionSortField.STATUS:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.status)
                    return select_clause.order_by(TAuction.status.desc())
                case AuctionSortField.SELLER:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.seller)
                    return select_clause.order_by(TAuction.seller.desc())
                case AuctionSortField.BID_ASSET:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.bid_asset_id.nullslast())
                    return select_clause.order_by(
                        TAuction.bid_asset_id.desc().nullslast()
                    )
                case AuctionSortField.MIN_BID:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.min_bid.nullslast())
                    return select_clause.order_by(TAuction.min_bid.desc().nullslast())
                case AuctionSortField.HIGHEST_BID:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.highest_bid.nullslast())
                    return select_clause.order_by(
                        TAuction.highest_bid.desc().nullslast()
                    )
                case AuctionSortField.START_TIME:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.start_time.nullslast())
                    return select_clause.order_by(
                        TAuction.start_time.desc().nullslast()
                    )
                case AuctionSortField.END_TIME:
                    if request.sort.asc:
                        return select_clause.order_by(TAuction.end_time.nullslast())
                    return select_clause.order_by(TAuction.end_time.desc().nullslast())
                case AuctionSortField.AUCTION_ASSET:
                    if request.sort.asc:
                        return select_clause.order_by(
                            TAuctionAsset.asset_id.nullslast()
                        )
                    return select_clause.order_by(
                        TAuctionAsset.asset_id.desc().nullslast()
                    )
                case AuctionSortField.AUCTION_ASSET_AMOUNT:
                    if request.sort.asc:
                        return select_clause.order_by(TAuctionAsset.amount.nullslast())
                    return select_clause.order_by(
                        TAuctionAsset.amount.desc().nullslast()
                    )
                case other:
                    raise AssertionError(
                        f"AuctionSortField match case is missing: {other}"
                    )

        count_query = build_where_clause(
            # pylint: disable=not-callable
            select(func.count(TAuction.app_id.distinct())).outerjoin(TAuction.assets)
        )

        logger.debug("count_query: %s", count_query)

        query = build_where_clause(select(TAuction).outerjoin(TAuction.assets))
        query = add_sort(query)
        query = query.limit(request.limit)
        query = query.offset(request.offset)
        # effectively dedupes the search results across the outer join
        query = query.group_by(TAuction.app_id)

        logger.debug("query: %s", query)

        with self._session_factory() as session:
            return AuctionSearchResult(
                total_count=session.scalar(count_query),
                auctions=[auction.to_auction() for auction in session.scalars(query)],
            )
