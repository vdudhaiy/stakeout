"""Tests for the /watchlist router's ticker resolution — specifically the
combined India option (see routers.watchlist._resolve_ticker): a bare Indian
ticker is no longer NSE-or-BSE picked by the user, it's resolved server-side
(NSE first, BSE as fallback), reusing whichever suffix an existing entry
already has.

stock_service.add_stock / get_all_stocks are mocked so these are offline —
add_stock is the "does this ticker exist" existence check the resolver
probes with; a ValueError from it means "not found on this exchange".
"""

from unittest.mock import patch, AsyncMock

from models.portfolio import WatchlistEntry

USER_ID = "test-user"  # matches conftest's TEST_USER_ID, used by the `client` fixture


async def test_add_bare_indian_ticker_defaults_to_nse(client):
    with patch("routers.watchlist.stock_service.get_all_stocks", new_callable=AsyncMock, return_value={}):
        with patch("routers.watchlist.stock_service.add_stock", new_callable=AsyncMock) as mock_add:
            resp = await client.post("/watchlist/RELIANCE?exchange=IN")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "RELIANCE.NS"
    assert "RELIANCE.NS" in data["stocks"]
    mock_add.assert_any_await("RELIANCE.NS")


async def test_add_bare_indian_ticker_falls_back_to_bse_when_nse_not_found(client):
    async def fake_add_stock(ticker):
        if ticker == "TMCV.NS":
            raise ValueError(f"Error creating stock data for {ticker}: not found")

    with patch("routers.watchlist.stock_service.get_all_stocks", new_callable=AsyncMock, return_value={}):
        with patch("routers.watchlist.stock_service.add_stock",
                   new_callable=AsyncMock, side_effect=fake_add_stock):
            resp = await client.post("/watchlist/TMCV?exchange=IN")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "TMCV.BO"
    assert "TMCV.BO" in data["stocks"]


async def test_add_bare_indian_ticker_400s_when_neither_exchange_has_it(client):
    with patch("routers.watchlist.stock_service.get_all_stocks", new_callable=AsyncMock, return_value={}):
        with patch("routers.watchlist.stock_service.add_stock",
                   new_callable=AsyncMock, side_effect=ValueError("not found")):
            resp = await client.post("/watchlist/BOGUS?exchange=IN")

    assert resp.status_code == 400
    assert "NSE or BSE" in resp.json()["detail"]


async def test_add_reuses_existing_bse_entry_without_probing(client, db_session):
    """A ticker already on the user's watchlist under BSE (e.g. from before
    this feature) should be recognized as already-added, not re-probed and
    forked into a second NSE entry."""
    db_session.add(WatchlistEntry(
        user_id=USER_ID, ticker="RELIANCE.BO", market="IN", company_name="Reliance Industries",
    ))
    await db_session.commit()

    with patch("routers.watchlist.stock_service.add_stock", new_callable=AsyncMock) as mock_add:
        resp = await client.post("/watchlist/RELIANCE?exchange=IN")

    assert resp.status_code == 200
    data = resp.json()
    assert data["exist"] is True
    assert data["ticker"] == "RELIANCE.BO"
    mock_add.assert_not_called()


async def test_add_us_ticker_unaffected_by_indian_resolution(client):
    with patch("routers.watchlist.stock_service.get_all_stocks", new_callable=AsyncMock, return_value={}):
        with patch("routers.watchlist.stock_service.add_stock", new_callable=AsyncMock) as mock_add:
            resp = await client.post("/watchlist/AAPL?exchange=US")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAPL"
    mock_add.assert_awaited_once_with("AAPL")


async def test_add_already_suffixed_ticker_skips_resolution(client):
    """A manually-typed '.NS'/'.BO' ticker is unambiguous even with
    exchange='IN' — no NSE-then-BSE probing needed."""
    with patch("routers.watchlist.stock_service.get_all_stocks", new_callable=AsyncMock, return_value={}):
        with patch("routers.watchlist.stock_service.add_stock", new_callable=AsyncMock) as mock_add:
            resp = await client.post("/watchlist/RELIANCE.BO?exchange=IN")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "RELIANCE.BO"
    mock_add.assert_awaited_once_with("RELIANCE.BO")
