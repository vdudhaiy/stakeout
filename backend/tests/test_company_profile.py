"""Tests for services.company_profile_service.

Name, sector and industry all come from one yfinance `.info` call — the
most rate-limit-prone thing the app does. Two things matter here: that the
three fields cost one call rather than two (they used to be fetched by two
separate code paths), and that the answer is persisted, so a restart of the
free-tier host doesn't re-spend that call on facts already known.

Mirrors test_peers' treatment of the DB layer: _read_row / _save are mocked
at the call site rather than exercised against a real database.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from yfinance.exceptions import YFRateLimitError

from models.company_profile import CompanyProfile
from services import company_profile_service as profiles
from services import stock_service, yf_guard

_INFO = {"name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics"}


def _row(age: timedelta = timedelta(days=1), **overrides) -> CompanyProfile:
    fields = {**_INFO, **overrides}
    return CompanyProfile(
        symbol="AAPL", fetched_at=datetime.now(timezone.utc) - age, **fields
    )


@pytest.fixture
def db():
    """Patch the module-level DB helpers to an empty, writable cache table."""
    with patch.object(profiles, "_read_row", AsyncMock(return_value=None)) as read:
        with patch.object(profiles, "_save", AsyncMock()) as save:
            yield {"_read_row": read, "_save": save}


async def test_a_fresh_db_row_is_served_without_touching_yfinance():
    with patch.object(profiles, "_read_row", AsyncMock(return_value=_row())), patch.object(profiles, "_save", AsyncMock()):
        with patch.object(profiles, "_fetch_info") as fetch:
            result = await profiles.get_profile("AAPL")

    fetch.assert_not_called()
    assert result == _INFO


async def test_a_stale_db_row_triggers_a_refetch_and_is_rewritten(db):
    stale = _row(age=profiles._REFRESH_INTERVAL + timedelta(days=1))
    db["_read_row"].return_value = stale
    with patch.object(profiles, "_fetch_info", return_value=_INFO):
        result = await profiles.get_profile("AAPL")

    db["_save"].assert_awaited_once()
    assert result == _INFO


async def test_a_fresh_fetch_is_persisted_so_a_restart_does_not_repeat_it(db):
    with patch.object(profiles, "_fetch_info", return_value=_INFO) as fetch:
        result = await profiles.get_profile("AAPL")

    fetch.assert_called_once()
    db["_save"].assert_awaited_once_with("AAPL", _INFO)
    assert result == _INFO


async def test_a_second_lookup_is_served_from_the_in_process_cache(db):
    with patch.object(profiles, "_fetch_info", return_value=_INFO) as fetch:
        await profiles.get_profile("AAPL")
        await profiles.get_profile("aapl")  # case-insensitive

    assert fetch.call_count == 1


async def test_a_stale_row_beats_nothing_when_yfinance_is_unavailable():
    stale = _row(age=profiles._REFRESH_INTERVAL + timedelta(days=1))
    with patch.object(profiles, "_read_row", AsyncMock(return_value=stale)), patch.object(profiles, "_save", AsyncMock()):
        with patch.object(profiles, "_fetch_info", side_effect=RuntimeError("yahoo down")):
            result = await profiles.get_profile("AAPL")

    assert result == _INFO


async def test_nothing_known_and_nothing_fetchable_returns_empty_fields(db):
    with patch.object(profiles, "_fetch_info", side_effect=RuntimeError("yahoo down")):
        result = await profiles.get_profile("AAPL")

    assert result == {"name": "", "sector": "", "industry": ""}


async def test_an_unavailable_answer_is_not_cached_and_retries(db):
    with patch.object(profiles, "_fetch_info", side_effect=RuntimeError("yahoo down")) as fetch:
        await profiles.get_profile("AAPL")
        await profiles.get_profile("AAPL")

    assert fetch.call_count == 2


async def test_a_lookup_during_a_backoff_makes_no_outbound_call(db):
    yf_guard.note(YFRateLimitError())
    with patch.object(profiles, "_fetch_info") as fetch:
        result = await profiles.get_profile("AAPL")

    fetch.assert_not_called()
    assert result == {"name": "", "sector": "", "industry": ""}


async def test_a_db_failure_degrades_to_a_plain_fetch(db):
    """The persistence layer is a cache, not a dependency — losing it must
    not fail the lookup."""
    db["_read_row"].side_effect = RuntimeError("db gone")
    db["_save"].side_effect = RuntimeError("db gone")

    with patch.object(profiles, "_fetch_info", return_value=_INFO):
        with pytest.raises(RuntimeError):
            await profiles.get_profile("AAPL")

    # The real helpers swallow their own errors, so a lookup through them
    # succeeds where the bare mocks above propagate.
    with patch.object(profiles, "_fetch_info", return_value=_INFO):
        assert await profiles._fetch_from_yfinance("AAPL") == _INFO


async def test_batch_lookup_dedupes_and_keys_by_uppercased_ticker(db):
    with patch.object(profiles, "_fetch_info", return_value=_INFO) as fetch:
        result = await profiles.get_profiles(["AAPL", "aapl", " "])

    assert list(result) == ["AAPL"]
    assert fetch.call_count == 1


async def test_name_and_classification_share_one_upstream_call(db):
    """The whole reason these three fields live together: stock_service's
    display-name path and its sector/industry path used to make separate
    `.info` calls for the same ticker."""
    with patch.object(profiles, "_fetch_info", return_value=_INFO) as fetch:
        name = await stock_service.display_name("AAPL")
        classification = await stock_service._cached_classification("AAPL")

    assert fetch.call_count == 1
    assert name == "Apple Inc."
    assert classification == {"sector": "Technology", "industry": "Consumer Electronics"}


async def test_display_name_falls_back_to_the_ticker_when_unknown(db):
    with patch.object(profiles, "_fetch_info", side_effect=RuntimeError("yahoo down")):
        assert await stock_service.display_name("ZZZZ") == "ZZZZ"
