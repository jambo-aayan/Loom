# 20. Position sizing, capital budget, and co-holding

## Status

Accepted

## Context

The universe is about to grow from 4 instruments to ~30, and further after that. Measured
against a 30-instrument universe, the current roster proposes about **17 entry signals per
trading day** (Compounder 8.6, Trend Follower 4.0, Harvester 3.9). Nothing in the system treats
that as a problem, because nothing in the system has a view on how many trades it can afford.

Three separate holes show up under that load.

**Sizing decays with each trade in a pass.** `size_and_check` caps a position at
`account_value × max_position_size_pct` but then requires `account.cash >= position_value`, and
cash falls as the pass executes. With a £5,000 account at 10%, the first signal gets £400 and
the tenth gets £155. Ordering within a pass is not a risk decision, but it is currently making
one — and the later, smaller positions are the ones where the `Round-trip cost` (ADR 0019) is a
larger share of the outcome.

**There is no bound on signal volume.** The exposure cap is the only backstop, and it binds
only after the money is committed. Seventeen signals a day against a cap that permits 90%
invested means the account fills up, and then every subsequent signal — including better ones —
is rejected for "insufficient cash or exposure headroom." The strategies do not compete on
quality; they compete on being early.

**Two strategies wanting the same instrument is undefined.** The per-instrument cap is applied
inside a single sizing call, not across `Book`s. Two `Book`s can independently take 10%
positions in the same name and the account holds 20% of it, which no limit describes. And 99%
of Trend Follower's measured entries coincide with the Harvester's exit condition on the same
instrument — so opposing orders in the same pass are the normal case, not an edge case.

## Decision

### Size against account value, cap by cash

A position's target size is `account_value × allocation`. Available cash caps it but does not
define it: if cash cannot fund the target, the position is funded to what cash allows, and if
that falls below the minimum below, the signal is skipped rather than shrunk.

This makes size a property of the signal rather than of its position in the queue. The
consequence is that a pass can run out of cash with signals still unserved, which is correct and
visible, rather than the current behaviour of serving everything at silently shrinking size.

### A capital budget per pass

Each pass has a budget: the total new capital it may commit, derived from the account's
uncommitted headroom. Signals are admitted against it, best first by `Confidence`, until it is
exhausted. Signals that do not fit are not executed.

This is the bound that was missing. The exposure cap says how much of the account may be
invested in total; the budget says how fast it may get there. Without it, the only mechanism
limiting a 17-signal day is running out of money, which selects for arrival order rather than
quality.

Rejected: rate-limiting signals per strategy per day. It caps the wrong thing — a strategy
having a good day is not a reason to ignore its signals — and it makes the limit
strategy-local when the scarce resource is account-wide.

> **Amended while designing the Low-Vol Compounder (ADR 0021).** This originally said signals are
> admitted best-first by `Confidence`. That was wrong on two counts.
>
> The immediate problem is that confidence is not comparable across strategies. Every entry
> confidence in the roster is an ad-hoc placeholder on its own scale — `0.5 + (threshold − vol)/
> threshold` for the Compounder, a flat `0.75`/`0.65` for the Trend Follower, `0.6 + squeeze
> ratio` for the Breakout — standing in for the per-bucket calibration ADR 0009 specifies and the
> code's own comments acknowledge as pending. That was harmless while confidence only met a
> per-strategy approval threshold; comparing the numbers to each other is new, and they do not
> survive it. The Compounder scores a clean 1.0 on any tracker at half its volatility gate and
> proposes ~8.6 entries a day, so it would out-rank a Trend Follower golden cross — 13 of those in
> six years — every pass, and take the budget every pass.
>
> The deeper problem survives calibration. Confidence is a probability, and ranking scarce capital
> by probability funds whatever is right most often rather than whatever is worth most. A
> reversion design that is right 70% of the time for a small gain would beat a trend design right
> 35% of the time for a large one, permanently, and the roster's best trades would never get
> funded.
>
> The budget therefore ranks by `Expected value` (see `CONTEXT.md`) — confidence weighed against
> the gain and loss the signal's own `Exit plan` describes, less the instrument's `Round-trip
> cost`. Loom derives it from what the signal already carries, so no strategy supplies it and no
> strategy can inflate it. `Confidence` keeps its existing job of meeting an `Approval mode`
> threshold, unchanged.
>
> An earlier proposal to interleave strategies round-robin was rejected: it treats the symptom
> and leaves capital allocated by arrival order within each strategy.

### No separate cash reserve

The account-wide exposure cap (currently 90%) already implies one: 10% of account value stays
uninvested by construction. Adding an explicit reserve on top would be the same constraint
expressed twice, in two places that would drift apart.

### A minimum position size

Positions below roughly £50 are not opened. Below that, the `Round-trip cost` and the spread are
a large enough fraction of the position that the trade cannot clear the cost floor from ADR
0019 regardless of whether the signal was right. A signal that can only be funded below the
minimum is skipped, not shrunk to fit.

### One instrument may be held by several Books

Co-holding is allowed, and is a shape we want: a long-term holding in one `Book` while another
`Book` trades around it — core-plus-satellite. The Low-Vol Compounder in particular is intended
to work as a high-frequency small-wins engine on instruments the account may also hold for the
long term.

Each `Book` keeps its own lots and its own `Exit plan` for them. The broker sees only the
aggregate; attribution is Loom's (ADR 0010), and reconciliation already works at lot level.

### One account-wide per-instrument cap

Concentration is a property of the account, not of a `Book`. The per-instrument limit is
therefore checked across every `Book` plus `Manual` — the same scope the exposure cap and kill
switch already use — rather than per-`Book`.

A per-`Book` allocation limit remains available as an additional layer on top, but it is not a
substitute: three `Book`s each under their own limit can still leave the account
over-concentrated in one name.

### Opposing orders in one pass: defer the entry, never the exit

When one `Book` would buy an instrument in the same pass that another would sell it, the sell
proceeds and the buy is deferred to the next pass.

Buying and selling the same instrument on the same day leaves net exposure unchanged and pays
the `Round-trip cost` twice for the privilege. One of the two has to yield, and it is the entry:
an exit is either an `Exit plan` firing — a commitment made at entry that ADR 0018 exists to
honour — or a strategy's judgment that it wants out now. An entry is an opportunity, and
opportunities recur. Deferring is also cheap to reverse: if the entry still qualifies next pass,
it fires next pass.

Netting the two internally was rejected: it would silently transfer a position between `Book`s
at a price neither strategy chose, and destroy the attribution that `Book`s exist to provide.

### The Low-Vol Compounder is `trading`, not `investment`

ADR 0009 tags it `investment`. That is wrong, and the code — which tags it `trading` — is right.

The Compounder is the roster's workhorse: frequent, small, largely automated trades against
short-term fluctuation, not a conviction-based long hold. `style` gates the research tier (ADR
0009), and pointing the expensive research tier at the highest-volume strategy in the roster is
exactly backwards. ADR 0009 is corrected in place.

## Consequences

- `size_and_check` changes shape: it needs account value and a pass-level budget, not just the
  account's current cash, and it gains a minimum-size rejection. Both the live trading pass and
  the backtest engine call it, so backtest results shift — again correctly, since the backtest
  has been modelling a sizing rule the live system will no longer use.
- Signals can now be rejected for "budget exhausted" rather than executed small. That needs to
  be visible in the UI and retained on the `Signal`, and those signals still deserve a
  `Counterfactual outcome` — a signal dropped for lack of capital is exactly the kind whose
  hypothetical outcome is worth knowing.
- Admitting signals best-first by `Confidence` makes confidence load-bearing across strategies,
  not just within one. Per-strategy confidence is not currently calibrated to be comparable
  between strategies (ADR 0009's calibration work is per-bucket, per-strategy), so cross-strategy
  ranking is an approximation until it is.
- Co-holding means "the position in X" is no longer a single object. Any UI or reconciliation
  path that assumes one lot chain per instrument needs to handle several, and an `Exit plan`
  firing must close only its own `Book`'s lots.
- Whether the Compounder gets its own narrower universe is left to its deep dive; this ADR only
  fixes what its `style` says about it.
