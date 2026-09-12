# Blackheart Self-Improvement Loop — Spec & Rollout

**Owner:** operator (rifki) · **Authored:** 2026-06-22 · **Mode chosen:** Both tracks in parallel
(scale proven edge + continuous research) · **Live autonomy:** auto-deploy within hard risk caps
(operator notified, can veto).

> Goal: a closed cycle that continuously *finds* the best strategies and *deploys capital to proven
> edge* — turning research output into real P&L, then feeding live results back into research.

---

## 0. Live ground truth (snapshot 2026-06-22, from prod DB)

| Fact | Value | Implication |
|---|---|---|
| Live trades / 30d | **3** | Book is dormant; real profit ≈ $0 |
| Account equity | ~$156 (TRADING) | Profit is capital-capped; caps below are %-of-equity so they scale |
| Live enabled strats (real) | 7 | Several are falsified — see hygiene list |
| Carry book live? | **No** — 1 real attempt FAILED 2026-06-20 | Blocked on `fix/quant-audit-2026-06-21` (carry mis-size) |

**Live strategies (enabled, non-simulated):**
- HEDGING: `EMA_BAND_BTC` 1d (50%) ✅ research-supported · `VMT_BTC` 1d (50%) ⚠️ beta/falsified
- TRADING: `DCB` BTC-4h (20%) ✅ · `DCB` ETH-1h (20%) ✅ (the one clean live edge) · `VRP_BTC` 1d (20%) ⚠️ uncertifiable ·
  `ATR_MOM` ETH-1h (10%) ⚠️ unsupported · `ALT_CAP_FADE_ZEC` 1h (10%) ⚠️ family falsified

---

## 1. The loop (one cycle)

```
        ┌──────────────────────────────────────────────────────────────┐
        │  (1) RESEARCH      quant-researcher → orchestrator tick loop   │  research-only,
        │  (2) REVIEW        run-pending-specialists (skeptic/PM/ML)     │  never touches
        │  (3) GRADUATE      frozen V11/V60 gate → approval inbox        │  live capital
        └───────────────┬──────────────────────────────────────────────┘
                        │ candidate passes server-side V102 live gate
                        ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  (4) DEPLOY-BRIDGE  auto-approve + allocate capital WITHIN     │  NEW component,
        │                     hard caps (this is the "auto-deploy")      │  operator-vetoable,
        │  (5) MONITOR        live P&L + per-strat DD → circuit-breaker  │  ARMED flag gated
        │  (6) HYGIENE        cut strats that decay below the gate       │
        └───────────────┬──────────────────────────────────────────────┘
                        │ live P&L + decay signals
                        └──────────────► feeds back into (1) RESEARCH
```

**Reuse, don't reinvent.** (1)-(3) already exist (quant-researcher, orchestrator :8082, specialist
agents, frozen gates). Only (4)-(6) are new, and they live **operator-side** (NOT in the
orchestrator — the orchestrator is sandboxed to the research account and must never promote to live).

---

## 2. Hard risk caps (the auto-deploy guardrails)

All capital references are **% of TRADING-book equity** so they scale when the book is funded.

| Cap | Default | Enforced by |
|---|---|---|
| Max capital / strategy | 20% | `capital_allocation_pct` clamp in deploy-bridge |
| Max total deployed | 80% (keep 20% buffer) | deploy-bridge pre-check |
| Max new auto-deploys / day | 1 | deploy-bridge rate limit |
| Mandatory per-strat gates | kill-switch ON, min-notional ON, V102 pass | refuse deploy otherwise |
| Per-strategy DD kill | 8% (`dd_kill_threshold_pct`) | existing per-strat kill-switch |
| **Book circuit-breaker** | halt all auto-deploy + alert if book DD-from-peak > 6% **or** daily loss > 4% | monitor |
| Carry leverage | ≤ 2× perp, positive-funding coins only, start 1 coin | carry deploy |
| New capital injection | **operator-only** — loop never adds funds | n/a |

`ARMED=false` by default. Auto-deploy runs **DRY_RUN** (logs intended action) until the operator
arms it after a clean dry-run + the safety rails are verified.

---

## 3. Staged rollout (each ▶ live-money step is a veto gate)

- **Stage 0 — Foundation (safe, now):** this spec + caps; deploy-bridge & monitor as DRY_RUN
  scripts; research heartbeat scheduled. No live change.
- **Stage 1 — Book hygiene ▶:** disable the 4 falsified live strats (`VMT_BTC`, `VRP_BTC`,
  `ATR_MOM`, `ALT_CAP_FADE_ZEC`); keep `DCB` ×2 + `EMA_BAND_BTC`. Stops capital dilution into dead edges.
- **Stage 2 — Carry unlock ▶:** land `fix/quant-audit-2026-06-21` (carry mis-size + kill-switch +
  dup-order fixes) → CI → VPS. Then deploy 1 positive-funding carry pair at ≤2× as a live canary.
- **Stage 3 — Arm auto-deploy ▶:** after a clean DRY_RUN cycle, set `ARMED=true`. Loop now
  auto-approves V102-passers + allocates within caps, monitored by the circuit-breaker.
- **Stage 4 — Scale:** widen carry to all positive-funding coins; operator funds the book; caps
  re-tuned to the larger equity.

---

## 4. Heartbeat

A scheduled Claude routine (cron) wakes on an interval and runs one cycle: ensure research is
progressing → drain specialists → run deploy-bridge (DRY_RUN until armed) → check circuit-breaker →
journal. The *intelligent* steps (research design, adversarial review) are agent-driven; the
*mechanical* steps (tick drive, monitor, bridge) are scripted.

---

## 5. DEPLOYED — durable, no-Claude-session loop (2026-06-23)

The loop now runs on the **VPS host crontab** (truly always-on; survives any session ending).
Two tiers:

| Cron | Cadence | Script | Role |
|---|---|---|---|
| `9 * * * *` | hourly | `loop/heartbeat.py` | **SAFETY** — read-only; Telegram-alert on FAILED trade (1h) / FAILED carry (1h) / naked futures leg. Detect-only, never trades. |
| `30 8 * * *` | daily 08:30 UTC | `loop/daily_cycle.py` | **INTELLIGENCE** — the thinking steps that used to need a Claude session. Posts one consolidated `loop_report` (DAILY) + Telegram if actionable. |
| dev-PC Task (every 3h) | 3-hourly | `loop/deadman/deadman_check.ps1` | **OFF-HOST DEAD-MAN'S** — runs on the dev PC (a8), independent of the VPS. Alerts Telegram if the newest `loop_report` is >36h stale OR the VPS is unreachable. Creds held locally so the alert fires even when the VPS is down. |

**`daily_cycle.py` does three jobs, then reports:**
- **(A) Carry profit** — re-rank sustained positive funding (liquid + has-spot + hedgeable) vs the
  live carry book; recommend the optimal rotation, then **execute it** (mode-gated). The execution
  path is **BUILT + sim-proven** (`--selftest` opens+closes a paper pair end-to-end, zero capital,
  PASS 2026-06-23). It rotates capital ONLY among **operator-seeded `FCARRY` rows** (never invents
  strategies on a cron — operator owns the universe, loop owns the allocation), enforces the caps
  (≤2× lev, ≥$20 notional, ≤`CAP_PAIRS`, **1 rotation/day**), closes-then-transfers-margin-then-opens,
  and ABORTS the whole rotation on any leg failure (naked-leg heartbeat is the backstop).
- **(B) Alpha-unlock watch** — free-data alpha is exhausted; the only unlock is new orthogonal data.
  Reads **`feature_values`** (where the orchestrator screens — NOT the unwired `feature_store`
  wide column) for `btc_rr25_skew_30d` / `btc_vol_term_spread` and reports accrual in days. The
  Deribit options-skew pipeline (`deribit_options` → `macro_raw` → `feature_values`) is **healthy
  and accruing since 2026-06-15** — just young (~7d as of 06-23). Fires WARN when it crosses the
  first-screen depth (90d, ≈ mid-Sept 2026) → spawn quant-researcher on the options-skew family;
  robust significance wants ~365d. Until then, stay data-gated; do **not** re-grind dead families.
- **(C) Circuit-breaker / hygiene** — naked legs + daily-loss-vs-4%-cap = CRITICAL; recent (6h)
  failures = WARN (the hourly heartbeat owns the urgent window; resolved bring-up noise ages out).

**Execution modes (`BH_LOOP_MODE`, cron default `report`):**
- `report` — recommend only, **no API calls** (current cron default; deploy is safe).
- `sim` — calls the carry endpoints with `simulated=true` (paper, no capital) — proves wiring live.
- `armed` — `simulated=false`, **real capital**.

**To ARM real-capital carry auto-rotation (two-key):** (1) prepend `BH_LOOP_MODE=armed ` to the
`daily_cycle.py` cron line, AND (2) create the token file `touch /home/starsky/blackheart/loop/.armed`.
Both are required — `MODE=armed` without the token is a safe no-op (it reports "armed-blocked" and
does not trade), so a stray cron edit can't move capital. Recommended sequence: run a few days in
`report`, then `sim` (paper) for a day, then arm. Disarm = `rm .armed`. Re-validate wiring any time
with `python3 daily_cycle.py --selftest`.

### Hardening (2026-06-23) — adversarial-review fixes
- **C1 — breaker now SEES carry P&L.** It reads the JVM `GET /api/v1/carry/pairs` (`totalPnl` =
  funding + basis MTM per live pair) + a **hedge-drift guard** (net base Δ > 10% of notional =
  CRITICAL). The old check read `strategy_daily_realized_curve`, which has 0 rows for carry → blind.
- **C2 — no capital-parking.** A rotation that aborts mid-way (close ok, open failed) no longer
  stamps the 1/day rate-limit, so the next run retries instead of leaving capital idle for a day.
- **D4 — net-positive funding band.** ENTRY floor `BH_MIN_FUNDING_PCT` (10%/yr gross, was 4% → could
  be net-negative) to rotate IN; lower EXIT floor `BH_EXIT_FUNDING_PCT` (3%) to hold vs cash — so a
  still-positive incumbent isn't dumped to 0%.
- **D5 — hysteresis** `BH_ROTATE_HYST` (1.25): swap an incumbent only for a challenger that beats it
  by ×1.25 — kills boundary churn.
- **C3 — market-cap quality floor.** ENTRY candidates must clear `BH_MIN_MCAP` ($100M, CoinGecko
  top-500). ENTRY-ONLY (never force-closes an incumbent — that's the funding band's job) and
  **fail-open** (CoinGecko outage → floor skipped, never empties the book). Stops the loop
  autonomously rotating into fragile micro-caps. (DEXE = ~$1.04B, clears it.)
- **R1** heartbeat dead-man's check (warns if the hourly log is >2h stale); **R2** arm-token + per-pair
  ceiling `BH_MAX_PAIR_NOTIONAL`; **R4** unlock uses *effective* depth `min(span, rows/24)`.
- **R1+ (dead-man's-switch) DONE — 3-layer monitoring.** (1) on-host hourly heartbeat (fast safety);
  (2) on-host daily cycle; (3) **off-host** dev-PC watcher every 3h that alerts if the loop goes
  silent (stale `loop_report`) or the VPS is down — the layer that survives a VPS reboot / cron death.
  Telegram alert-path verified end-to-end. Optional 4th layer pre-wired: set `BH_DEADMAN_URL` to a
  healthchecks.io check → the daily cycle pings it on success, so a fully-external always-on service
  alerts even if the dev PC is also off.
- **Still open (honest):** R3 — the DAILY `loop_report` write still depends on the JVM being up (the
  off-host watcher mitigates the *alerting* dependency, not the report write). D1/D2 (durable
  automation + a data-watch, not a learning/active-research system) are honest framing, not bugs.

**★ Honest framing (lead with this):** at ~$156 equity / ~$22 carry notional, funding profit is
literally cents/yr — **profit is capital-gated**, not code-gated. And **alpha is data-gated** — the
one fresh orthogonal surface (Deribit options-skew / vol-term) is plumbed and accruing correctly in
`feature_values` since 2026-06-15, but it's only ~7d deep; a first IC-screen is viable ~90d
(≈ mid-Sept 2026), robust ~1yr. The two real levers are operator inputs: **fund the book** and
**let the skew data accrue (or buy deeper/more orthogonal data)**. The loop is now durable and
self-running; it cannot manufacture edge that capital and data don't allow.
