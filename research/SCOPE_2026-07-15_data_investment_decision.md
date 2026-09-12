# Data-Investment Decision — Options/Skew vs Universe Expansion (2026-07-15)

## Why this is the real lever
Every strategy hunt this session (classical, ML, maker, ensemble) hit the same wall: the current data —
crypto majors' price / volume / funding — supports only real-but-modest edges, all correlated (BTC-beta) and
all regime-decayed post-2022. **More strategy construction on this data is exhausted.** A materially stronger
book needs NEW information or a LOWER-correlation universe. Two candidate investments:

---

## Option A — Options / Skew data (Deribit via Tardis)
**Cost:** ~$200–400 one-time (historical options-surface backfill).
**Readiness:** HIGH — the loader is already built (`deribit_options_history.py`, commit 147e14a); the
`feature_store` skew columns (`rr25_skew_*`, `dvol_*`, `vol_term_spread`) exist but are 0-row until data
lands; a pre-registered skew stress-gate hypothesis (`470ca035`) is Stage-0 ready to run the moment it does.
**What it unlocks (new information class):**
- Real implied-vol *surface* (not the realized-vol proxies that just blew up the short-vol sleeve) — skew,
  term structure, risk-reversal → **dealer positioning / vol-risk-premium done right**.
- Orthogonal to price/trend/funding → a candidate for a genuinely-uncorrelated **new sleeve** (exactly what
  the portfolio needs, since carry died and short-vol-on-proxies failed).
**Expected lift:** MODERATE, honest. The realized-vol short-vol sleeve failed (negative skew, blows up in
spikes) — real options data is *cleaner* but the vol-risk-premium is *genuinely tail-risky*, so it may confirm
"real but not free." The skew *stress-gate* (using skew to gate/size existing sleeves) is the higher-odds use
than a standalone short-vol strategy. Also unblocks the skew-conditioning of DCB/carry.
**Risk:** LOW cost, LOW downside — worst case it confirms no edge and you've spent ~$300. The harness is ready
so the $-to-answer latency is days, not months.
**★1-bar-lag trap:** the Deribit DVOL/skew candles are OPEN-STAMPED — any consumer needs `ts ≤ entry − 1
interval` (a latent DCB-style look-ahead). Wire the lag BEFORE any live skew gate.

---

## Option B — Universe expansion (breadth beyond crypto majors)
The correlation ceiling (all majors are BTC-beta) is THE structural cap on the daily book Sharpe. Breaking it
needs genuinely lower-correlation instruments. Two very different sub-options:

### B1 — More crypto alts (cheap, limited payoff)
**Cost:** low — engineering to plumb more symbols (data already partly present: ADA/DOGE/AVAX have 1h/4h
feature history; more alts = backfill + seed). Days, not weeks.
**Payoff:** LIMITED — more alts are *still BTC-beta* (correlation ~0.7–0.9 to BTC), so the diversification
benefit is small. Widens the XS-momentum basket and the carry universe marginally, but does NOT break the
correlation cap. Worth doing opportunistically, not as the structural fix.

### B2 — Non-crypto instruments (equities / FX / commodities / rates)
**Cost:** HIGH — a new venue + data plane + execution path. The second-exchange scoping put a first new venue
at ~10–15 person-days (one-time arch tax), and a non-crypto asset class is more (different market hours,
settlement, instruments). This is a platform-level expansion, not a feature.
**Payoff:** HIGHEST — genuinely uncorrelated return streams (equity trend, FX carry, commodity momentum) are
what actually breaks the crypto-correlation ceiling and lets the √N portfolio scale to a real Sharpe. This is
the true quant-firm endgame (many uncorrelated markets, not many strategies on one market).
**Risk:** HIGH cost/complexity; a multi-month commitment; needs capital to matter across more markets.

---

## Comparison

| | A: Options/Skew | B1: More alts | B2: Non-crypto |
|---|---|---|---|
| Cost | ~$200–400 | ~days eng | ~weeks–months eng + venue |
| Readiness | loader built, gate ready | data partly present | greenfield |
| New info class? | YES (IV surface) | no (same drivers) | YES (new markets) |
| Breaks correlation cap? | partial (vol is orthogonal-ish) | NO (BTC-beta) | **YES** |
| Expected lift | moderate | low | **high** |
| Risk | low | low | high |

## Recommendation — sequence, don't choose
1. **NOW: buy the options/skew data (Option A).** Cheapest, fastest, harness ready, adds a genuinely new
   information class + a candidate uncorrelated sleeve + skew-conditioning for existing sleeves. Low-risk,
   days-to-answer. This is the obvious first move.
2. **Opportunistically: B1 (more alts)** whenever plumbing is cheap — marginal, widens the XS/carry baskets,
   but don't expect it to break the ceiling.
3. **Strategically (the real endgame): B2 (non-crypto breadth)** — this is what actually raises the portfolio
   ceiling, but it's a deliberate multi-month platform investment gated on capital + commitment. Revisit once
   the portfolio machine (the risk-parity book) is live and there's capital + track record to justify it.

## The honest through-line
The portfolio framework is the *machine*; new data/markets are the *fuel*. Building the machine on the current
fuel gives a modest book. Options data is the cheap fuel top-up (do it now); non-crypto breadth is the fuel
that actually changes the game (do it deliberately, later). Neither is "more strategy research on crypto
majors" — which is done.
