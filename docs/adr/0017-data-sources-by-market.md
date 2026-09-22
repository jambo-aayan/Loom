# Data sources by market: Yahoo for LSE, Twelve Data for US only

Supersedes ADR-0008 for LSE listings (decision D25 in `docs/plan/02-decisions.md`; evidence in `docs/plan/09-phase0-findings.md`).

ADR-0008 chose Twelve Data as the primary market-data provider on the assumption that its free tier covered LSE listings. It doesn't: every LSE ETF in the universe (VUSA, CSP1, VUAG, ISF, VWRL) needs the paid "Grow" plan. The code had also been sending Yahoo-style symbols (`VUSA.L`) to Twelve Data, which doesn't recognise them, so LSE prices in production were in practice coming from the yfinance fallback. We now route by exchange: **Yahoo (yfinance) is primary for LSE daily and hourly bars; Twelve Data is primary for US listings, with Yahoo as fallback.** We don't pay for Twelve Data. The research was run on Yahoo bars, so LSE signals in the app use the same data they were tested on.

Because Yahoo is unofficial, three rules come with it: every request goes through an **instrument registry** that holds each source's exchange-qualified symbol (never a bare ticker, which can resolve to a EUR listing on another exchange); every response's reported unit must match the listing's quoting unit (GBp or GBP) before prices are normalised to GBP, and a mismatch is rejected rather than guessed; and **no data or stale data for an instrument means no entries for it in that scan**, with "stale" judged against the exchange calendar. Exits are unaffected, since they use Trading 212's own prices.

## Considered options

Paying for Twelve Data Grow would keep one provider for everything, but costs money for data the research never used. Keeping Twelve Data primary for LSE with a qualified symbol isn't possible on the free tier.

## Consequences

The Twelve Data call budget no longer limits the LSE universe or the hourly scan, so the planned two-step scan (build plan T4.3) is dropped. Yahoo's rate limits and occasional gaps become the main data risk: Yahoo requests must be batched and back off on HTTP 429, and the share of scans with fresh data is recorded for the health endpoint. Observed on 22 Sep 2026: Yahoo's daily bar for the current session can have no close for several hours after the LSE close, even though that day's hourly bars are present. The freshness rule treats that as stale.
