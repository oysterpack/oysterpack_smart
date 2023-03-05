"""
Service persistent state
"""
from dataclasses import dataclass
from typing import cast

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from oysterpack.apps.auction_app.commands.auction_algorand_search.search_auction_manager_events import (
    AuctionManagerEvent,
)
from oysterpack.apps.auction_app.data import Base
from oysterpack.apps.auction_app.domain.auction import AuctionManagerAppId
from oysterpack.apps.auction_app.domain.service_state import (
    SearchAuctionManagerEventsServiceState,
)


@dataclass
class TSearchAuctionManagerEvents(Base):
    """
    Stores state for the `SearchAuctionManagerEvents` command to enable paging
    to continue between application restarts.
    """

    __tablename__ = "search_auction_manager_events"

    # service that owns this state
    service_name: Mapped[str] = mapped_column(primary_key=True)
    auction_manager_app_id: Mapped[AuctionManagerAppId] = mapped_column(
        ForeignKey("auction_manager.app_id", ondelete="CASCADE"),
        primary_key=True,
    )
    event: Mapped[AuctionManagerEvent] = mapped_column(primary_key=True)
    min_round: Mapped[int | None] = mapped_column()
    next_token: Mapped[str | None] = mapped_column()

    def to_domain_object(self) -> SearchAuctionManagerEventsServiceState:
        return SearchAuctionManagerEventsServiceState(
            self.service_name,
            self.auction_manager_app_id,
            self.event,
            self.min_round,
            self.next_token,
        )

    @classmethod
    def create(
        cls,
        state: SearchAuctionManagerEventsServiceState,
    ) -> "TSearchAuctionManagerEvents":
        return cls(
            service_name=cast(Mapped[str], state.service_name),
            auction_manager_app_id=cast(
                Mapped[AuctionManagerAppId], state.auction_manager_app_id
            ),
            event=cast(Mapped[AuctionManagerEvent], state.event),
            min_round=cast(Mapped[int | None], state.min_round),
            next_token=cast(Mapped[str | None], state.next_token),
        )
