# Low-Vol Compounder — candidate universe

A working list, not a committed one. ADR 0021 restricts the Compounder to GBP-denominated,
LSE-listed index ETFs, because that is the only combination that avoids both T212 charges: no FX
conversion (the instrument's currency matches the account's) and no stamp duty (ETFs are exempt).
The whole design depends on a ~0.05-0.10% round trip instead of ~0.30%, so the universe *is* the
edge here as much as the entry rule is.

## Read this before using any ticker below

**Every entry must be verified against T212's own instrument metadata before it ships**, for two
reasons, and the second one is the dangerous one.

1. Availability. T212 does not list everything on the LSE, and its own ticker namespace differs
   from market-data tickers (`VUSA.L` is `VUSAl_EQ` to T212). Only the synced `instruments` table
   from ADR 0022 can confirm what is actually tradeable.
2. **Currency line.** Most of these funds have both a GBP line and a USD line on the LSE, often
   with near-identical names and similar tickers. Picking the USD line means paying 0.15% FX on
   every buy and every sell — which is the entire cost advantage, gone, and gone silently. The
   fund would still work; the strategy would not.

Treat the list below as "these funds are worth having", not "these tickers are correct". The
ticker column is a starting point for the lookup, not an answer.

## Candidates

Roughly 20, weighted toward broad, liquid, boring exposure. Spread matters more than fund choice
at this size — a niche sector tracker with a 0.3% spread gives back everything the GBP listing won.

### Core global and US

| Fund | Ticker (verify) |
| --- | --- |
| Vanguard S&P 500 | VUSA.L / VUAG.L |
| iShares Core S&P 500 | CSP1.L |
| Vanguard FTSE All-World | VWRL.L / VWRP.L |
| Vanguard FTSE Developed World | VEVE.L |
| iShares Core MSCI World | SWLD.L |
| HSBC MSCI World | HMWO.L |

### UK

| Fund | Ticker (verify) |
| --- | --- |
| iShares Core FTSE 100 | ISF.L |
| Vanguard FTSE 100 | VUKE.L |
| Vanguard FTSE 250 | VMID.L |
| iShares FTSE 250 | MIDD.L |

### Regional

| Fund | Ticker (verify) |
| --- | --- |
| Vanguard FTSE Developed Europe ex-UK | VERX.L |
| Vanguard FTSE Japan | VJPN.L |
| Vanguard FTSE Emerging Markets | VFEM.L |
| iShares Core MSCI EM IMI | EMIM.L |

### Income and factor

| Fund | Ticker (verify) |
| --- | --- |
| Vanguard FTSE All-World High Dividend Yield | VHYL.L |
| iShares UK Dividend | IUKD.L |

### Bonds — lower volatility, different behaviour

| Fund | Ticker (verify) |
| --- | --- |
| iShares Core UK Gilts | IGLT.L |
| Vanguard UK Gilt | VGOV.L |
| Vanguard Global Aggregate Bond, GBP hedged | VAGP.L |
| iShares Core Global Aggregate Bond, GBP hedged | AGBP.L |

## Notes on composition

**Overlap is real and mostly fine.** VUSA and CSP1 track the same index; VWRL, VEVE and SWLD
overlap heavily. For a reversion strategy this is not duplication so much as several shots at the
same dislocation — but it does mean the account can end up more concentrated in US large-cap than
the position count suggests. ADR 0020's account-wide per-instrument cap does not catch this,
because these are different instruments. Worth watching once there is data; not worth solving in
advance.

**The bond funds are in the list for a specific reason.** They move differently from the equity
funds and are quieter, so they are the most likely part of the universe to still be generating
entries when equities are in a regime the 50-day filter has shut off. They are also the entries
most likely to be too small to clear the ~£50 minimum, since a quieter fund dislocates less. If
they turn out to contribute nothing, cut them.

**Accumulating vs distributing** (VUSA vs VUAG, VWRL vs VWRP) does not matter much for a 10-day
hold, but pick one convention and stay with it — holding both lines of the same fund would be
the account-wide concentration problem above, with extra steps.

## Not included, deliberately

- Anything USD- or EUR-denominated, however good the fund. This is the whole point.
- Single-country emerging market, sector, thematic and small-cap funds — wider spreads.
- Leveraged, inverse, or synthetic-replication products.
- Individual shares. UK shares pay 0.5% stamp duty on purchase, which is more than six times the
  entire cost budget this strategy is built around.
