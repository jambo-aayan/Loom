# 06 · UI specification

**Visual reference:** `docs/design/loom-v4.html` (Claude Design, "Loom Minimal v4"). Open it in a browser; it is interactive. Match its layout, typography, colours and components. Where this document and the design disagree on *rules or numbers*, this document wins; on *look*, the design wins.

**Current frontend:** a functional scaffold (Next.js 14 + Tailwind, 9 pages, 2 components). It does not implement the design. Treat the UI as a rebuild on top of the existing API client (`frontend/lib/api.ts`) and PWA setup.

## Principles

- Minimal. Main screens show only: Loom value, pause control, market regime, open positions with exit levels, pending approvals. Everything else is one tap away.
- Every number has a plain-English reason. No uncalibrated "confidence" shown as a probability.
- AI content is labelled "Advisory" and collapsed by default.
- Demo and Live are never summed together.
- Mobile first; desktop layout as in the design.

## Build order

1. **Design tokens and shared components**: colours, type, spacing from v4; logo + wordmark; card; stat tile; chip/badge; toggle; exit-level progress bar (stop–price–target); signal card; section list (Settings); empty and loading states.
2. **Shell**: header (logo, nav, health dot, Demo/Live view switch, History, Settings, theme, Pause), regime line, pause/halt banners, bottom tabs on mobile.
3. **Approvals**, then **Overview** (highest daily use).
4. **Strategies** (list + detail tabs), **History**, **Settings**, **Insights**.
5. Remove the Backtest page and nav entry. Fold anything useful from the Performance page into Strategies/History.

## Screens

Legend for backend status: ✅ exists · 🔧 exists, needs change · 🆕 new backend work (see build plan).

### Shell
| Element | Data | Backend |
|---|---|---|
| Nav: Overview, Approvals (badge), Strategies, Insights; History & Settings as header icons | pending count | ✅ signals |
| Health dot → popover: last pass per job, T212/Twelve Data/Yahoo status, Twelve Data calls used today, dead-man's switch | job heartbeats, source status | 🆕 health endpoint |
| Demo / Live switch (view only) | environment | ✅ |
| Pause button (header) + banner "New trades paused — exits still protect open positions" + Resume | pause state + reason | 🆕 pause/halt |
| Halt banner (red) | halt state | 🔧 kill switch → halt |
| Regime line: "Market in uptrend · dip strategies active" / "Market below 200-day average · Crash-buyer active" | market index vs SMA200 | 🆕 regime endpoint |

### Overview
| Element | Data | Backend |
|---|---|---|
| Loom value, change since start, invested amount, equity curve | Loom value history (daily closes from summary job) | 🆕 |
| Today: opened, closed (+P/L), signals skipped (→ History tab), next scan time | day's events, skip log, schedule | 🆕 skip log |
| Review N signals button | pending count | ✅ |
| Open positions: ticker, strategy, £, P/L, stop–price–target bar, time left ("day 3 of 20", "27h left"), target note "updates daily" for Deep Dip | Loom lots + exit levels + T212 `currentPrice` | 🆕 exit levels, 🔧 live prices |
| Slots per strategy (used/total, sleeve, £/trade, shadow label, lending later) | sizing state | 🆕 |
| "Not managed by Loom" (collapsed): count and value of personal holdings | Manual book | ✅ |

### Approvals (signal card)
| Element | Data | Backend |
|---|---|---|
| Ticker, BUY, Demo/Live badge, strategy + version, fired time, expiry countdown | signal, config version, expiry | 🔧 expiry per strategy |
| £ amount, % of Loom budget, fractional quantity @ price | sizing preview | 🆕 |
| Why it fired: each condition with value and threshold (e.g. `−1.8σ · needs ≤ −1.5σ`) | per-condition values stored on the signal | 🆕 structured reasons |
| Spread check (only if live spread data exists) | quote with bid/ask | 🆕, optional |
| Exit plan: target (with rule and "updates daily" for Deep Dip), stop (with "catastrophe stop"), exit-by | proposed exit levels | 🆕 |
| Round-trip cost (% and £) | cost model | 🆕 |
| Group exposure after trade (`World group 14% → 25% · cap 25%`) | groups + exposure | 🆕 |
| AI note (collapsed, "Advisory") | screening insight | ✅ |
| Optional quick note | stored with approval | 🆕 small |
| Approve £X / Reject | | ✅ |
| "Decided today" panel | today's decisions + notes | 🔧 |

### Strategies
List: name, status (Off / Shadow / Active), one-line description, sleeve · slots · £/trade.

Detail header: name, version, description, status toggle, timeframe, max hold, sleeve, slots, per-trade £.

Tabs:
- **Performance**: *Research vs reality* table (win rate, avg return, avg hold, return per day held, real cost; research value vs actual). Verdict chip: **"Not enough trades yet · n/30"** until the gate count (30 Compounder, 20 Deep Dip), then "On track" (avg return ≥ half of research and win rate within 10 points) or "Below expectations". Cumulative return chart. 🆕 research baselines stored per config version.
- **Parameters**: Entry and Exit groups; each field: label, value + unit, one-line meaning, "Raising this means…", allowed range. Save → new config version (confirmation shows diff). Values and ranges from `03-strategy-specs.md`. 🔧 config versions exist (JSON) → typed schema.
- **Versions**: history, compare, promote, roll back. ✅/🔧
- **Shadow configs**: add an alternative parameter set; shows its would-be trades and research-vs-reality alongside. 🆕
- **Universe**: instruments grouped by instrument group, with exclusions and reasons. 🆕

### History
- Filters: environment (defaults to current, **never "Demo + Live" summed**), strategy, exit reason (target / stop / time / strategy exit / manual).
- Summary tiles: net P/L (current environment), win rate, avg cost real vs modelled.
- Trades table: date, instrument, £, strategy, exit reason + held time, return (£, %), cost real/modelled, **what happened next** for time exits ("+0.8% 20 days later", "−0.4% 45 hrs later", "tracking…").
- **Skipped signals** tab: signal, strategy, reason. 🆕

### Insights
- "Ask about anything" box (✅ ask endpoint).
- Instrument search → **instrument page**: price chart with Loom entries/exits marked, fundamentals, latest advisory research note, "you hold this personally" flag, which strategies can trade it and why not if excluded. 🆕 page, ✅ most data.
- Daily summaries archive, one expandable card per day. 🔧 digest endpoint.

### Settings
Sections 1 and 2 open by default; others collapsed with a one-line status on the right.

1. **Safety**: status line; Pause new trades (same as header); Halt everything (typed confirmation); Live trading (typed confirmation); Global auto-approval; Daily loss limit % (pauses); Budget kill switch % (pauses).
2. **Budget**: Loom budget £; Demo notional size £; Reinvest profits; Cash reserve %; Excluded instruments (auto from personal holdings, labelled, plus manual additions).
3. **Risk profile**: Conservative / Balanced / Aggressive; group cap; single stock cap; minimum trade; capital lending (disabled until Phase 4).
4. **Strategy shortcuts**: link to each strategy's Parameters tab.
5. **Schedule**: entry scan cadence (read-only: hourly), exit check interval, market sessions, daily summary time.
6. **Notifications**: email and push toggles, each with **Send test**; per-event toggles (approvals, pause/halt, failed orders, missed runs, daily summary).
7. **Connections & health** (read-only): T212 (environment, API key scopes), Twelve Data (calls used/800), Yahoo, last pass per job, dead-man's switch.
8. **AI insights**: auto research on/off; monthly paid-research cap with spend so far.
9. **Instrument groups**: auto groups, threshold (0.95), manual overrides.

Footer: "All changes are logged" → change log (setting, old → new, when). 🆕 settings audit log.

Field validation: every numeric field has bounds; out-of-range input is rejected inline, never silently clamped.
