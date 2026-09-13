# IDX — "No falling knives", read as a quant (2026-09-13)

**The operator's principle.** Do not buy what is still falling; do not hold through a market fall. Both halves exist as
book options (entry gate, regime filter). This note measures what the principle is worth, first in the data, then as
the combined rule the paper book runs.

## 1. What buying a falling name actually returns (monthly panel 2021–2025, 12-month forward return)

| All liquid names, by 12-1 momentum | mean | median | P(< −30 %) | P(> +50 %) |
|---|---|---|---|---|
| Q1 falling | −1.1 % | −13.1 % | 30 % | 9 % |
| Q2 | +7.6 % | −7.1 % | 20 % | 10 % |
| Q3 | +12.7 % | −5.2 % | 15 % | 11 % |
| Q4 | +11.5 % | −6.0 % | 20 % | 14 % |
| Q5 rising hard | +7.6 % | −20.9 % | 39 % | 17 % |

| All liquid names, by drawdown from the 252-day high | mean | median | P(< −30 %) |
|---|---|---|---|
| Q1 deepest | +2.0 % | −21.5 % | 40 % |
| Q5 at the high | +9.1 % | −5.8 % | 20 % |

In the whole market the principle is right: the falling fifth has a negative mean and a −13 % median, the deeply fallen
fifth a −21 % median with a 40 % chance of losing another 30 %. Both extremes are bad; the middle is where the return is.

| Strict-gate names only (the value book's pool) | mean | median | P(< −30 %) | P(> +50 %) |
|---|---|---|---|---|
| momentum Q1 falling | +2.3 % | −4.2 % | 21 % | 9 % |
| momentum Q5 rising | +9.9 % | −10.6 % | 26 % | 14 % |
| drawdown Q1 deepest | +3.3 % | −6.5 % | 27 % | 12 % |
| drawdown Q5 at the high | −1.3 % | −5.9 % | 16 % | 6 % |
| **cheap (E/P above the pool median) and momentum bottom half** | **+11.5 %** | **−0.9 %** | **12 %** | 10 % |
| cheap and momentum top half | +9.5 % | −5.1 % | 12 % | 10 % |

Inside the quality gate the knife loses its edge: cheap names still falling did *better* than cheap names rising, on mean
and median, with the same left tail. The gate has already removed the knives that fall for a reason (losses, cash burn,
leverage); what is left falling is mostly price, and price that has fallen on a sound business is what value buys.

## 2. The combined rule (pre-registered; script `idx_no_knife.py`; trials cumulative 126)

Strict composite, four calendars, monthly checks, drift with a one-slot cap, cash 4 %/yr.

| Arm | May: CAGR · Sharpe · mDD | Feb | Aug | Nov |
|---|---|---|---|---|
| none | 17.9 · 1.00 · 22 % | 24.0 · 1.41 · 21 % | 16.7 · 0.95 · 19 % | 13.0 · 0.81 · 22 % |
| entry gate only | 16.8 · 1.14 · 15 % | 18.1 · 1.29 · 18 % | 15.8 · 1.02 · 20 % | 13.5 · 0.99 · 16 % |
| regime filter only | 13.9 · 0.94 · 22 % | 15.1 · 1.17 · 18 % | 16.7 · 1.14 · 15 % | 11.9 · 0.93 · 20 % |
| regime + entry gate (the paper book) | 12.6 · 1.08 · 12 % | 10.5 · 1.05 · 11 % | 15.1 · 1.26 · 15 % | 10.1 · 1.00 · 11 % |
| regime + entry only when 20 % off the low | 11.7 · 1.07 · 12 % | 9.9 · 1.03 · 11 % | 13.2 · 1.18 · 15 % | 9.0 · 0.95 · 11 % |

Reading rule (combined preferred over the filter alone only if shallower worst drawdown and within 10 % of its return in
three calendars): drawdown yes (15 % against 22 %), return no (0 of 4). **The filter alone stays the crash rule; the entry
gate stays optional.** The stricter "already turned" entry is worse on every count: it only delays.

## 3. The frontier, which is what a quant actually chooses on

Per calendar the arms line up as a return-for-drawdown trade: from 17–24 % CAGR at 19–22 % drawdown (none) to 10–15 %
at 11–15 % (both rules). Two observations:

- **The entry gate raises the Sharpe in three calendars of four** (1.14 vs 1.00, 1.02 vs 0.95, 0.99 vs 0.81; Feb the
  exception) and takes 2–7 points off the drawdown for 1–6 points of return. It is the efficient way to buy less pain.
- **The regime filter is dominated inside this window** (same drawdown as none in two calendars, less return) and only
  earns its keep in the crash years outside it (2008, 2020: drawdowns halved on the 2008–2026 basket). It is insurance:
  negative expected value in calm years, positive over a full cycle, and invisible in five years without a crash.

The combined rule is therefore the "no falling knives" principle in full: the smoothest path of all (11–15 % drawdown,
Sharpe 1.0–1.3) at the lowest return (10–15 %). Whether that trade is worth it depends on one number the data cannot
supply: the drawdown at which the operator sells.

## 4. What it means today (2026-09-11)

The IHSG is 11 % under its 200-day average: the regime filter says cash. Five of the ten strict names are under their own
average (BBNI, ASII, CTRA, PWON, ACES); the entry gate alone would buy GJTL, SRTG, SIMP, LSIP now and the rest at the
monthly check they cross. The full principle says: wait.
