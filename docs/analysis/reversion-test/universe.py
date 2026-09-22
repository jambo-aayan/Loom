"""Candidate universe from docs/compounder-universe-candidates.md.

The doc is explicit that the ticker column is "a starting point for the lookup, not an answer",
and that the GBP-vs-USD line is the dangerous failure. `resolve` below is the check: it fetches
each ticker and records the currency the provider reports, so a USD line shows up as a USD line
rather than silently becoming a 0.30%-cost instrument wearing a GBP thesis.
"""

from __future__ import annotations

# (fund, ticker, bucket). Both lines listed where the doc lists both.
CANDIDATES: list[tuple[str, str, str]] = [
    ("Vanguard S&P 500 (dist)", "VUSA.L", "core"),
    ("Vanguard S&P 500 (acc)", "VUAG.L", "core"),
    ("iShares Core S&P 500", "CSP1.L", "core"),
    ("Vanguard FTSE All-World (dist)", "VWRL.L", "core"),
    ("Vanguard FTSE All-World (acc)", "VWRP.L", "core"),
    ("Vanguard FTSE Developed World", "VEVE.L", "core"),
    ("iShares Core MSCI World", "SWLD.L", "core"),
    ("HSBC MSCI World", "HMWO.L", "core"),
    ("iShares Core FTSE 100", "ISF.L", "uk"),
    ("Vanguard FTSE 100", "VUKE.L", "uk"),
    ("Vanguard FTSE 250", "VMID.L", "uk"),
    ("iShares FTSE 250", "MIDD.L", "uk"),
    ("Vanguard FTSE Dev Europe ex-UK", "VERX.L", "regional"),
    ("Vanguard FTSE Japan", "VJPN.L", "regional"),
    ("Vanguard FTSE Emerging Markets", "VFEM.L", "regional"),
    ("iShares Core MSCI EM IMI", "EMIM.L", "regional"),
    ("Vanguard FTSE All-World High Div", "VHYL.L", "income"),
    ("iShares UK Dividend", "IUKD.L", "income"),
    ("iShares Core UK Gilts", "IGLT.L", "bond"),
    ("Vanguard UK Gilt", "VGOV.L", "bond"),
    ("Vanguard Global Agg Bond GBP-h", "VAGP.L", "bond"),
    ("iShares Core Global Agg Bond GBP-h", "AGBP.L", "bond"),
]

TICKERS = [t for _, t, _ in CANDIDATES]
BUCKET = {t: b for _, t, b in CANDIDATES}
FUND = {t: f for f, t, _ in CANDIDATES}

# Annualised vol used only by the null-control generator, chosen per bucket to be in the right
# neighbourhood for that kind of fund. These are inputs to a synthetic control, never a claim
# about the real funds.
NULL_PROFILE: dict[str, tuple[float, float]] = {
    "core": (0.08, 0.15),
    "uk": (0.05, 0.16),
    "regional": (0.06, 0.17),
    "income": (0.05, 0.16),
    "bond": (0.01, 0.06),
}

NULL_START_PRICE = {"core": 60.0, "uk": 7.0, "regional": 25.0, "income": 50.0, "bond": 12.0}
