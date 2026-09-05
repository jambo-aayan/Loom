# Scheduled single-pass runtime, not a long-running daemon

The trading job is a single entrypoint (`run_trading_pass(environment)`) that does one full pass — fetch account/positions/history, evaluate strategies, size, execute within risk limits, exit — invoked either manually (CLI) or by a scheduler (cron locally, a cloud scheduler later), rather than a persistent process with an internal poll loop.

This fits both the domain and the API's constraints: Trading 212's rate limits are per-account and header-driven rather than fixed intervals, which a self-pacing persistent loop would need to manage carefully, while discrete scheduled passes sidestep that entirely. It also suits the trading style (low-volatility, patient strategies, not high-frequency) — there's no need for continuous low-latency polling. The always-on dashboard/API service is a separate process from this job; they share the same database.
