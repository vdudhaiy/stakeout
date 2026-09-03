"""Daily closing levels for a market index, kept for as long as they're useful.

Deliberately a separate table from market_data rather than a few extra rows
in it. market_data is the *tradeable* universe: get_symbols() enumerates it
to drive the stocks list, the industry/sector maps and the startup repair
jobs, so putting ^GSPC in there would make an index show up everywhere a
ticker is expected.

Persisted for the same reason as company_profile: a benchmark comparison
needs years of daily closes, they are settled history that can never change,
and the free-tier host restarts many times a day. Holding them only in
memory means re-downloading a decade of index data to redraw the same chart.
See services.index_service.get_history for the incremental fetch that fills
gaps without ever re-asking for a bar it already has.
"""

from datetime import date as date_

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Date

from database import Base


class IndexHistory(Base):
    __tablename__ = "index_history"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)  # Yahoo caret symbol, e.g. "^GSPC"
    date: Mapped[date_] = mapped_column(Date, primary_key=True)
    close: Mapped[float] = mapped_column(Float)


class IndexHistoryRefresh(Base):
    """The window of an index's history that has already been asked for.

    Same idea as market_data.ArchiveRefresh: without it, every request that
    lands after a session closes but before Yahoo publishes the bar sees a
    stale table and asks again, and every restart repeats that. `covered_to`
    is the last completed session already fetched *for*, so a newer session
    invalidates it on its own with nothing having to expire.

    `covered_from` records how far *back* we have asked, which is not the
    same as the oldest row stored. A caller asking from a Sunday gets a first
    bar dated Monday, so comparing the request against the oldest stored row
    would decide history was still missing and re-download the whole series
    on every single request. Recording the request, not the answer, is what
    makes "fetched once" actually mean once.
    """

    __tablename__ = "index_history_refresh"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    covered_from: Mapped[date_] = mapped_column(Date)
    covered_to: Mapped[date_] = mapped_column(Date)
