"""Instrument catalogue and ticker resolution (ADR-0022).

Drives through the real entrypoints (the sync service and the CLI command) against a real
database, faking only the broker — the boundary the Testing Decisions in issue #1 name.
"""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner

from loom import db, instruments
from loom.cli.main import cli
from loom.execution.broker import BrokerInstrument, FakeBrokerClient
from loom.execution.t212_client import Trading212Client
from loom.execution.t212_tickers import (
    LOOM_TO_T212,
    DbTickerMap,
    StaticTickerMap,
    UnmappedInstrumentError,
    derive_loom_ticker,
)
from loom.models import AssetType, Instrument


@pytest.mark.parametrize(("loom_ticker", "t212_ticker"), sorted(LOOM_TO_T212.items()))
def test_derivation_reproduces_every_confirmed_mapping(loom_ticker: str, t212_ticker: str):
    """The four entries in LOOM_TO_T212 were confirmed against a real T212 account, so they are
    the oracle for the inference in derive_loom_ticker. If T212's ticker format ever drifts this
    fails here, rather than the sync quietly renaming the universe."""
    short_name = loom_ticker.removesuffix(".L")
    assert derive_loom_ticker(t212_ticker, short_name) == loom_ticker


def test_unnameable_venue_is_skipped_not_guessed():
    # A venue suffix we have never confirmed. Guessing would store a position under a ticker
    # that resolves to the wrong instrument — the exact failure UnmappedInstrumentError exists
    # to prevent, so the row is skipped instead.
    assert derive_loom_ticker("ABCq_EQ", "ABC") is None
    assert derive_loom_ticker("EURUSD", None) is None


def test_sync_is_idempotent(session):
    first = instruments.sync_instruments(session, FakeBrokerClient())
    assert first.added == 4 and first.updated == 0

    second = instruments.sync_instruments(session, FakeBrokerClient())
    assert (second.added, second.updated, second.unchanged) == (0, 0, 4)


def test_sync_updates_changed_metadata(session):
    instruments.sync_instruments(session, FakeBrokerClient())

    renamed = FakeBrokerClient(
        instruments=[BrokerInstrument("TSLA", "TSLA_US_EQ", "Tesla, Inc.", "USD", "share", "NASDAQ", None, 0.5)]
    )
    result = instruments.sync_instruments(session, renamed)

    assert result.updated == 1
    row = instruments.get(session, "TSLA")
    assert row.name == "Tesla, Inc."
    assert row.min_trade_quantity == 0.5


def test_colliding_loom_tickers_are_reported_and_skipped(session):
    instruments.sync_instruments(session, FakeBrokerClient())
    before = instruments.get(session, "VUSA.L").t212_ticker

    clash = FakeBrokerClient(
        instruments=[BrokerInstrument("VUSA.L", "VUSAother_EQ", "Another listing", "USD", "etf")]
    )
    result = instruments.sync_instruments(session, clash)

    assert result.added == 0
    assert len(result.conflicts) == 1
    assert "VUSA.L" in result.conflicts[0]
    # The incumbent is untouched: positions may already be recorded against it.
    assert instruments.get(session, "VUSA.L").t212_ticker == before


def test_sync_records_currency_and_asset_type(session):
    """The two fields ADR-0019's cost model needs: FX applies when the currency differs from the
    account's, and UK stamp duty applies to a share but not an ETF."""
    instruments.sync_instruments(session, FakeBrokerClient())

    etf = instruments.get(session, "VUSA.L")
    share = instruments.get(session, "TSLA")
    assert (etf.currency, etf.asset_type) == ("GBP", AssetType.etf)
    assert (share.currency, share.asset_type) == ("USD", AssetType.share)


def test_search_prefers_an_exact_ticker_match(session):
    instruments.sync_instruments(session, FakeBrokerClient())

    assert [r.loom_ticker for r in instruments.search(session, "vanguard")] == ["VUSA.L", "VWRL.L"]
    assert instruments.search(session, "TSLA")[0].loom_ticker == "TSLA"
    assert instruments.search(session, "   ") == []


def test_db_ticker_map_resolves_synced_instruments(session):
    session.add(
        Instrument(
            loom_ticker="AAPL", t212_ticker="AAPL_US_EQ", name="Apple", currency="USD",
            asset_type=AssetType.share,
        )
    )
    session.commit()

    tickers = DbTickerMap(session)
    assert tickers.to_t212("AAPL") == "AAPL_US_EQ"
    assert tickers.from_t212("AAPL_US_EQ") == "AAPL"


def test_db_ticker_map_falls_back_to_the_static_map(session):
    """A fresh database has no synced rows yet, so the original four instruments must still
    trade — otherwise the sync becomes a prerequisite for the system working at all."""
    tickers = DbTickerMap(session)
    assert tickers.to_t212("VUSA.L") == "VUSAl_EQ"

    with pytest.raises(UnmappedInstrumentError, match="run the instrument sync"):
        tickers.to_t212("NOT.A.TICKER")


def test_t212_client_parses_metadata_and_skips_unusable_rows():
    rows = [
        {"ticker": "TSLA_US_EQ", "shortName": "TSLA", "name": "Tesla", "type": "STOCK",
         "currencyCode": "USD", "isin": "US88160R1014", "minTradeQuantity": 0.1},
        {"ticker": "VUSAl_EQ", "shortName": "VUSA", "name": "Vanguard S&P 500", "type": "ETF",
         "currencyCode": "GBP", "minTradeQuantity": "0.1"},
        {"ticker": "CRUDE_OIL", "name": "A commodity", "type": "COMMODITY"},  # not an equity
        {"ticker": "XYZq_EQ", "shortName": "XYZ", "type": "STOCK"},  # unconfirmed venue
        {"ticker": "", "name": "junk"},
        "not even a dict",
    ]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=rows))
    client = Trading212Client(
        "https://x", "k", "s", client=httpx.Client(transport=transport, base_url="https://x")
    )

    parsed = client.get_instruments()

    assert [i.loom_ticker for i in parsed] == ["TSLA", "VUSA.L"]
    assert parsed[0].asset_type == "share"
    assert parsed[1].asset_type == "etf"
    assert parsed[1].min_trade_quantity == 0.1  # string in the payload, float on the way out


def test_unrecognised_asset_type_becomes_other_rather_than_a_guess():
    rows = [{"ticker": "ABC_US_EQ", "shortName": "ABC", "type": "WARRANT", "currencyCode": "USD"}]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=rows))
    client = Trading212Client(
        "https://x", "k", "s", client=httpx.Client(transport=transport, base_url="https://x")
    )

    # Guessing "share" here would apply 0.5% stamp duty to something that may not owe it.
    assert client.get_instruments()[0].asset_type == "other"


def test_static_map_is_the_default_when_no_tickers_are_injected():
    client = Trading212Client("https://x", "k", "s", client=httpx.Client(base_url="https://x"))
    assert isinstance(client._tickers, StaticTickerMap)


def test_cli_sync_instruments_reports_what_it_did(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/loom.db")
    db.init_db(f"sqlite:///{tmp_path}/loom.db")

    result = CliRunner().invoke(cli, ["sync-instruments", "--environment", "demo"])

    assert result.exit_code == 0, result.output
    assert "4 instrument(s) for demo" in result.output
    assert "4 added" in result.output
