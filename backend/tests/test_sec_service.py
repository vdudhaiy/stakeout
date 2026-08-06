"""Tests for sec_service — the free SEC ticker-registry fallback for company
names. httpx is faked directly (no real network calls); no existing test in
this repo exercises the raw httpx.AsyncClient path, so this defines its own
minimal fake rather than reusing a shared helper.
"""

import httpx
import pytest
from unittest.mock import patch

from cache import sec_ticker_cache
from services import sec_service


@pytest.fixture(autouse=True)
def _clear_sec_cache():
    sec_ticker_cache.clear()
    yield
    sec_ticker_cache.clear()


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient's `async with ... as client: await client.get(url)` usage."""

    def __init__(self, response=None, exc=None, **kwargs):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        if self._exc:
            raise self._exc
        return self._response


_SAMPLE_DATA = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
}


async def test_company_name_returns_match():
    fake_client = _FakeAsyncClient(response=_FakeResponse(_SAMPLE_DATA))
    with patch("services.sec_service.httpx.AsyncClient", return_value=fake_client):
        name = await sec_service.company_name("AAPL")
    assert name == "Apple Inc."


async def test_company_name_is_case_insensitive_and_strips_whitespace():
    fake_client = _FakeAsyncClient(response=_FakeResponse(_SAMPLE_DATA))
    with patch("services.sec_service.httpx.AsyncClient", return_value=fake_client):
        name = await sec_service.company_name(" aapl ")
    assert name == "Apple Inc."


async def test_company_name_returns_none_for_unknown_ticker():
    fake_client = _FakeAsyncClient(response=_FakeResponse(_SAMPLE_DATA))
    with patch("services.sec_service.httpx.AsyncClient", return_value=fake_client):
        name = await sec_service.company_name("RELIANCE.NS")
    assert name is None


async def test_ticker_map_is_cached_across_calls():
    fake_client = _FakeAsyncClient(response=_FakeResponse(_SAMPLE_DATA))
    with patch("services.sec_service.httpx.AsyncClient", return_value=fake_client) as mock_client_cls:
        await sec_service.company_name("AAPL")
        await sec_service.company_name("MSFT")
    mock_client_cls.assert_called_once()  # second lookup served from sec_ticker_cache


async def test_ticker_map_network_failure_returns_none_not_raises():
    fake_client = _FakeAsyncClient(exc=httpx.ConnectError("network down"))
    with patch("services.sec_service.httpx.AsyncClient", return_value=fake_client):
        name = await sec_service.company_name("AAPL")
    assert name is None


async def test_ticker_map_http_error_returns_none_not_raises():
    fake_client = _FakeAsyncClient(response=_FakeResponse({}, status_code=403))
    with patch("services.sec_service.httpx.AsyncClient", return_value=fake_client):
        name = await sec_service.company_name("AAPL")
    assert name is None
