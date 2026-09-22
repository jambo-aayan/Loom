"""The market-data boundary (T0.3): symbol mapping, routing by exchange (D25), unit checks and
GBp → GBP normalisation (invariant 9), and freshness (no fresh data → no entries)."""

from datetime import UTC, date, datetime

import httpx
import pytest

from loom.calendars import Exchange
from loom.execution.t212_tickers import from_t212, to_t212
from loom.instruments import Instrument, UnmappedInstrumentError, get_instrument
from loom.market_data.boundary import NoMarketDataError, RawHistory, UnitMismatchError, normalise
from loom.market_data.freshness import StaleDataError, is_daily_fresh, is_hourly_fresh
from loom.market_data.routed import RoutedMarketDataSource
from loom.market_data.twelve_data import TwelveDataSource
from loom.strategy import Bar, InstrumentHistory

PENCE_ETF = Instrument("CSP1.L", Exchange.LSE, "GBP", "GBp", "CSP1l_EQ", "CSP1.L", "CSP1")
BAR = Bar("2026-09-21", 60900.0, 61100.0, 60800.0, 60962.0, 1000.0)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


class _FakeQuoteSource:
    def __init__(self, name, unit="GBP", bars=(BAR,), raises=False):
        self.name = name
        self.unit = unit
        self.bars = bars
        self.raises = raises
        self.requested: list[Instrument] = []

    def fetch_daily(self, instrument, start, end):
        self.requested.append(instrument)
        if self.raises:
            raise RuntimeError(f"{self.name} down")
        return RawHistory(symbol="x", reported_unit=self.unit, bars=self.bars)


# --- units ----------------------------------------------------------------------------------


def test_pence_prices_are_normalised_to_pounds():
    history = normalise(PENCE_ETF, RawHistory("CSP1.L", "GBp", (BAR,)), "yahoo")
    bar = history.bars[0]
    assert (bar.open, bar.high, bar.low, bar.close) == pytest.approx((609.0, 611.0, 608.0, 609.62))
    assert bar.volume == 1000.0  # volume is a share count, not a price
    assert history.currency == "GBP"


def test_gbx_alias_is_treated_as_pence():
    assert normalise(PENCE_ETF, RawHistory("CSP1.L", "GBX", (BAR,)), "yahoo").bars[0].close == pytest.approx(609.62)


def test_pound_quoted_listing_is_left_as_is():
    history = normalise(get_instrument("VUSA.L"), RawHistory("VUSA.L", "GBP", (BAR,)), "yahoo")
    assert history.bars[0].close == BAR.close


@pytest.mark.parametrize("reported", ["GBP", "EUR", "USD", None, ""])
def test_a_unit_other_than_the_listings_quoting_unit_is_rejected(reported):
    # CSP1 is quoted in pence: "GBP" would mean the source changed units under us (or it's a
    # different listing), and prices would be 100x off. Refuse rather than guess.
    with pytest.raises(UnitMismatchError):
        normalise(PENCE_ETF, RawHistory("CSP1.L", reported, (BAR,)), "yahoo")


def test_a_currency_mismatch_is_rejected():
    usd_listing = get_instrument("TSLA")
    with pytest.raises(UnitMismatchError):
        normalise(usd_listing, RawHistory("TSLA", "GBP", (BAR,)), "twelve_data")


# --- symbol mapping and routing -------------------------------------------------------------


def test_registry_maps_every_namespace():
    vusa = get_instrument("VUSA.L")
    assert (vusa.exchange, vusa.yahoo_symbol, vusa.twelve_data_symbol, vusa.t212_ticker) == (
        Exchange.LSE,
        "VUSA.L",
        "VUSA",
        "VUSAl_EQ",
    )
    assert to_t212("TSLA") == "TSLA_US_EQ" and from_t212("VWRLl_EQ") == "VWRL.L"


def test_unknown_instrument_never_reaches_a_source():
    yahoo, twelve = _FakeQuoteSource("yahoo"), _FakeQuoteSource("twelve_data", unit="USD")
    source = RoutedMarketDataSource(yahoo=yahoo, twelve_data=twelve)
    with pytest.raises(UnmappedInstrumentError):
        source.get_history("VUSA", "2026-09-01", "2026-09-21")
    assert yahoo.requested == [] and twelve.requested == []


def test_lse_listings_go_to_yahoo_only():
    yahoo, twelve = _FakeQuoteSource("yahoo"), _FakeQuoteSource("twelve_data", raises=True)
    source = RoutedMarketDataSource(yahoo=yahoo, twelve_data=twelve)
    source.get_history("VUSA.L", "2026-09-01", "2026-09-21")
    assert [i.id for i in yahoo.requested] == ["VUSA.L"]
    assert twelve.requested == []


def test_us_listings_go_to_twelve_data_then_fall_back_to_yahoo():
    twelve, yahoo = _FakeQuoteSource("twelve_data", unit="USD"), _FakeQuoteSource("yahoo", unit="USD")
    RoutedMarketDataSource(yahoo=yahoo, twelve_data=twelve).get_history("TSLA", "2026-09-01", "2026-09-21")
    assert len(twelve.requested) == 1 and yahoo.requested == []

    twelve_down = _FakeQuoteSource("twelve_data", raises=True)
    RoutedMarketDataSource(yahoo=yahoo, twelve_data=twelve_down).get_history("TSLA", "2026-09-01", "2026-09-21")
    assert len(yahoo.requested) == 1


def test_a_unit_mismatch_is_not_papered_over_by_the_fallback():
    twelve, yahoo = _FakeQuoteSource("twelve_data", unit="EUR"), _FakeQuoteSource("yahoo", unit="USD")
    with pytest.raises(UnitMismatchError):
        RoutedMarketDataSource(yahoo=yahoo, twelve_data=twelve).get_history("TSLA", "2026-09-01", "2026-09-21")
    assert yahoo.requested == []


def test_every_source_failing_raises_but_empty_answers_give_an_empty_history():
    down = _FakeQuoteSource("yahoo", raises=True)
    with pytest.raises(NoMarketDataError):
        RoutedMarketDataSource(yahoo=down).get_history("VUSA.L", "2026-09-01", "2026-09-21")
    empty = _FakeQuoteSource("yahoo", bars=())
    assert RoutedMarketDataSource(yahoo=empty).get_history("VUSA.L", "2026-09-01", "2026-09-21").bars == ()


def test_twelve_data_requests_name_the_exchange_and_report_the_currency():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(
            200,
            json={
                "meta": {"symbol": "TSLA", "currency": "USD", "exchange": "NASDAQ"},
                "values": [{"datetime": "2026-09-21", "open": "1", "high": "2", "low": "0.5", "close": "1.5"}],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.twelvedata.com")
    raw = TwelveDataSource(api_key="k", client=client).fetch_daily(get_instrument("TSLA"), "2026-09-01", "2026-09-21")
    assert seen["symbol"] == "TSLA" and seen["exchange"] == "NASDAQ"
    assert raw.reported_unit == "USD" and raw.bars[0].close == 1.5


def test_yfinance_end_date_is_inclusive_and_currency_is_reported(monkeypatch):
    import pandas as pd
    import yfinance

    from loom.market_data.yfinance_source import YFinanceSource

    calls = {}

    class _Ticker:
        history_metadata = {"currency": "GBp"}

        def __init__(self, symbol):
            calls["symbol"] = symbol

        def history(self, start, end, interval):
            calls["end"] = end
            index = pd.DatetimeIndex([pd.Timestamp("2026-09-21", tz="Europe/London")])
            return pd.DataFrame(
                {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [10]}, index=index
            )

    monkeypatch.setattr(yfinance, "Ticker", _Ticker)
    raw = YFinanceSource().fetch_daily(PENCE_ETF, "2026-09-01", "2026-09-21")
    assert calls == {"symbol": "CSP1.L", "end": "2026-09-22"}  # yfinance's end is exclusive
    assert raw.reported_unit == "GBp" and raw.bars[0].date == "2026-09-21"


# --- freshness ------------------------------------------------------------------------------


def test_daily_freshness_follows_the_calendar():
    tue_pre_open = utc(2026, 9, 22, 6, 45)
    assert is_daily_fresh(date(2026, 9, 21), Exchange.LSE, tue_pre_open)
    assert not is_daily_fresh(date(2026, 9, 18), Exchange.LSE, tue_pre_open)  # Monday's bar is missing
    # Monday pre-open: Friday's bar is the latest there should be.
    assert is_daily_fresh(date(2026, 9, 25), Exchange.LSE, utc(2026, 9, 28, 6, 45))


def test_hourly_freshness_requires_the_just_closed_bar():
    now = utc(2026, 9, 22, 9, 5)  # 10:05 BST: the 09:00 BST bar just closed
    assert is_hourly_fresh(utc(2026, 9, 22, 8, 0), Exchange.LSE, now)
    assert not is_hourly_fresh(utc(2026, 9, 22, 7, 0), Exchange.LSE, now)  # one bar behind


def test_routed_source_flags_stale_history():
    source = RoutedMarketDataSource(yahoo=_FakeQuoteSource("yahoo"), now=lambda: utc(2026, 9, 23, 6, 45))
    fresh = InstrumentHistory("VUSA.L", (Bar("2026-09-22", 1, 1, 1, 1),))
    stale = InstrumentHistory("VUSA.L", (Bar("2026-09-21", 1, 1, 1, 1),))
    source.check_fresh(fresh)
    with pytest.raises(StaleDataError):
        source.check_fresh(stale)
    with pytest.raises(StaleDataError):
        source.check_fresh(InstrumentHistory("VUSA.L", ()))
