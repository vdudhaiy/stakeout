"""Tests for services.finnhub_client — the shared low-level Finnhub HTTP
call used by peers_service, logo_service, and quote_service.

No pre-emptive local rate limiting (Finnhub's own free-tier budget is the
only cap) — a real 429 from Finnhub triggers a cooldown instead, honoring
Retry-After when present.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

from services import finnhub_client


def _mock_client(response: MagicMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_get_no_api_key_returns_none():
    with patch("services.finnhub_client.FINNHUB_API_KEY", None):
        result = await finnhub_client.get("/stock/peers", {"symbol": "AAPL"})
    assert result is None


async def test_get_success_returns_parsed_json():
    response = MagicMock(status_code=200)
    response.json.return_value = {"logo": "https://example.com/aapl.png"}
    response.raise_for_status = MagicMock()

    with patch("services.finnhub_client.FINNHUB_API_KEY", "test-key"):
        with patch("services.finnhub_client.httpx.AsyncClient", return_value=_mock_client(response)):
            result = await finnhub_client.get("/stock/profile2", {"symbol": "AAPL"})

    assert result == {"logo": "https://example.com/aapl.png"}


async def test_get_transport_error_returns_none():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=ConnectionError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.finnhub_client.FINNHUB_API_KEY", "test-key"):
        with patch("services.finnhub_client.httpx.AsyncClient", return_value=mock_client):
            result = await finnhub_client.get("/stock/peers", {"symbol": "AAPL"})

    assert result is None


# ── 429 cooldown ──────────────────────────────────────────────────────────────

@patch.object(finnhub_client, "_cooldown_until", 0.0)
async def test_get_429_enters_cooldown_and_returns_none():
    response = MagicMock(status_code=429, headers={"Retry-After": "30"})

    with patch("services.finnhub_client.FINNHUB_API_KEY", "test-key"):
        with patch("services.finnhub_client.httpx.AsyncClient", return_value=_mock_client(response)):
            with patch("services.finnhub_client.time.monotonic", return_value=1000.0):
                result = await finnhub_client.get("/quote", {"symbol": "AAPL"})

    assert result is None
    assert finnhub_client._cooldown_until == 1030.0


@patch.object(finnhub_client, "_cooldown_until", 0.0)
async def test_get_429_without_retry_after_uses_default_cooldown():
    response = MagicMock(status_code=429, headers={})

    with patch("services.finnhub_client.FINNHUB_API_KEY", "test-key"):
        with patch("services.finnhub_client.httpx.AsyncClient", return_value=_mock_client(response)):
            with patch("services.finnhub_client.time.monotonic", return_value=1000.0):
                await finnhub_client.get("/quote", {"symbol": "AAPL"})

    assert finnhub_client._cooldown_until == 1000.0 + finnhub_client._DEFAULT_COOLDOWN_SECONDS


async def test_get_skips_request_while_in_cooldown():
    with patch("services.finnhub_client.FINNHUB_API_KEY", "test-key"):
        with patch("services.finnhub_client._cooldown_until", time.monotonic() + 30):
            with patch("services.finnhub_client.httpx.AsyncClient") as mock_cls:
                result = await finnhub_client.get("/quote", {"symbol": "AAPL"})

    assert result is None
    mock_cls.assert_not_called()


async def test_get_resumes_after_cooldown_expires():
    with patch("services.finnhub_client.FINNHUB_API_KEY", "test-key"):
        with patch("services.finnhub_client._cooldown_until", time.monotonic() - 1):
            response = MagicMock(status_code=200)
            response.json.return_value = {"c": 100}
            response.raise_for_status = MagicMock()
            with patch("services.finnhub_client.httpx.AsyncClient", return_value=_mock_client(response)):
                result = await finnhub_client.get("/quote", {"symbol": "AAPL"})

    assert result == {"c": 100}
