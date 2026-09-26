#!/usr/bin/env python3
"""Formal multiple-testing corrections for the combined book (operator 2026-09-26: "okay coba lakukan 1 - 6", item 1).

Phase 1 (#380) gave the Deflated Sharpe only as a RANGE (0.23 .. 0.70) because the effective number of independent trials is
unknown. This audit adds the two standard families of corrections. Declared before any result was seen; audit, no trial.

  (a) DATA-SNOOPING on the construction grid (the 144 configurations of #380, daily returns, 2022-01 -> 2026-09-16), benchmark
      = COMPOSITE (IHSG) total daily return. Loss differential d_k,t = r_k,t - r_bench,t.
      - Hansen (2005) SPA test, consistent p-value, stationary bootstrap (Politis-Romano, mean block 10 sessions, B = 2,000):
        H0 = no configuration beats IHSG in expected daily return.
      - Romano-Wolf (2005) stepdown on the studentised mean differentials: which configurations beat IHSG with the family-wise
        error rate held at 5 %, and does the DEPLOYED one survive.
      This answers "is the construction search itself luck?". It cannot answer whether the SIGNALS were luck (they are held
      fixed in the grid) - (b) does that.
  (b) THE DESK'S LEDGER (Harvey, Liu & Zhu 2016 / Harvey & Liu 2015 haircut): t = Sharpe x sqrt(years) for the deployed book
      (#348, 4.7 years) against M tests. The ledger's 6,406 stored arm Sharpes (170 studies) are converted to t-stats with the
      same 4.7 years (most IDX studies cover 2020/22-26; the few 2005-26 ones make this conservative for them) and give the
      p-value population for BHY. M = 100 / 300 / 1,019 (effective independent tests unknown -> a range, stated as such).
      Reported: the multiple-testing-adjusted p-value (Bonferroni, Holm, BHY) and the haircut Sharpe = the Sharpe whose
      single-test p-value equals the adjusted one.
READ-ONLY; one idx.study row (multiple_testing, kind audit).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "multiple_testing"
NAVS = os.path.join(ROOT, "research-scratch", "phase1_navs.pkl")
DEPLOYED = "ens4|stop5|floor30|g10/t5/m10"
B, BLOCK, SEED = 2000, 10, 20260926
YEARS = 4.7
SHARPE_DEP = 2.21
M_GRID = (100, 300, 1019)


def stationary_bootstrap_idx(n: int, block: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano: geometric block lengths with mean ``block``, wrapping around."""
    idx = np.empty(n, dtype=int)
    t = rng.integers(n)
    p = 1.0 / block
    for i in range(n):
        idx[i] = t
        t = rng.integers(n) if rng.random() < p else (t + 1) % n
    return idx


def spa_and_rw(D: np.ndarray, names: list[str]) -> dict:
    """D: n x K daily differentials vs the benchmark. -> SPA consistent p-value, Romano-Wolf stepdown rejections."""
    n, K = D.shape
    rng = np.random.default_rng(SEED)
    dbar = D.mean(0)
    boots = np.empty((B, K))
    for b in range(B):
        boots[b] = D[stationary_bootstrap_idx(n, BLOCK, rng)].mean(0)
    omega = np.sqrt(n) * boots.std(0, ddof=1)                        # bootstrap sd of sqrt(n) * mean
    omega = np.where(omega > 0, omega, 1e-12)
    tstat = np.sqrt(n) * dbar / omega
    # SPA (consistent): recentre only the configurations that are not clearly bad
    thr = -np.sqrt(2 * np.log(np.log(n))) * omega / np.sqrt(n)
    mu_c = np.where(dbar >= thr, dbar, 0.0)
    T_spa = max(tstat.max(), 0.0)
    T_boot = np.maximum((np.sqrt(n) * (boots - mu_c) / omega).max(1), 0.0)
    p_spa = float((T_boot >= T_spa).mean())
    # Romano-Wolf stepdown on the studentised means (centred bootstrap)
    Z = np.sqrt(n) * (boots - dbar) / omega                            # B x K, the null distribution of each t
    active = np.ones(K, bool)
    rejected = np.zeros(K, bool)
    while active.any():
        crit = np.quantile(Z[:, active].max(1), 0.95)
        new = active & (tstat > crit)
        if not new.any():
            break
        rejected |= new
        active &= ~new
    dep = names.index(DEPLOYED)
    # per-configuration RW adjusted p-value for the deployed one: share of bootstrap maxima (over all K) >= its t
    p_rw_dep = float((Z.max(1) >= tstat[dep]).mean())
    order = np.argsort(-tstat)
    return {"n": int(n), "K": int(K), "spa_p": p_spa, "spa_T": float(T_spa), "rw_rejected": int(rejected.sum()),
            "deployed_t": float(tstat[dep]), "deployed_rejected": bool(rejected[dep]), "deployed_p_rw_single_step": p_rw_dep,
            "deployed_excess_ann": float(dbar[dep] * 252), "best": names[int(order[0])], "best_t": float(tstat[order[0]]),
            "worst_rejected_t": float(tstat[rejected].min()) if rejected.any() else None}


def ledger_sharpes(conn) -> np.ndarray:
    vals = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (int, float)) and k.lower() in ("sharpe", "sh") and np.isfinite(v):
                    vals.append(float(v))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for (s,) in conn.execute("SELECT summary FROM idx.study WHERE summary IS NOT NULL").fetchall():
        walk(json.loads(s) if isinstance(s, str) else s)
    a = np.array(vals)
    return a[(a > -3) & (a < 6)]


def bhy_adjusted(p_all: np.ndarray, p_target: float, M: int) -> float:
    """BHY (Benjamini-Hochberg-Yekutieli) adjusted p-value of ``p_target`` when the M tests look like ``p_all`` (resampled to M)."""
    rng = np.random.default_rng(SEED)
    ps = np.sort(np.append(rng.choice(p_all, M - 1, replace=True), p_target))
    c = np.sum(1.0 / np.arange(1, M + 1))
    adj = np.minimum.accumulate((ps * M * c / np.arange(1, M + 1))[::-1])[::-1]
    return float(min(1.0, adj[np.searchsorted(ps, p_target)]))


def holm_adjusted(p_all: np.ndarray, p_target: float, M: int) -> float:
    rng = np.random.default_rng(SEED)
    ps = np.sort(np.append(rng.choice(p_all, M - 1, replace=True), p_target))
    adj = np.maximum.accumulate(ps * (M - np.arange(M)))
    return float(min(1.0, adj[np.searchsorted(ps, p_target)]))


def haircut(p_adj: float) -> float:
    """The annual Sharpe whose single-test two-sided p-value over YEARS equals p_adj."""
    if p_adj >= 1:
        return 0.0
    return float(stats.norm.ppf(1 - p_adj / 2) / np.sqrt(YEARS))


def main() -> int:
    store = "--no-store" not in sys.argv
    dsn = AF.dsn()
    navs = pd.read_pickle(NAVS)
    R = navs.pct_change().dropna()
    with psycopg.connect(dsn) as conn:
        comp = pd.read_sql("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' ORDER BY 1", conn)
        sh = ledger_sharpes(conn)
    comp["trade_date"] = pd.to_datetime(comp["trade_date"])
    bench = comp.set_index("trade_date")["close"].astype(float).pct_change().reindex(R.index).fillna(0.0)
    D = R.sub(bench, axis=0).to_numpy()
    a = spa_and_rw(D, list(R.columns))
    t_dep = SHARPE_DEP * np.sqrt(YEARS)
    p_dep = float(2 * (1 - stats.norm.cdf(t_dep)))
    p_all = 2 * (1 - stats.norm.cdf(np.abs(sh * np.sqrt(YEARS))))
    b = {"t": float(t_dep), "p_single": p_dep, "ledger_arms": int(len(sh)), "rows": {}}
    for M in M_GRID:
        bon = min(1.0, p_dep * M)
        hol, bh = holm_adjusted(p_all, p_dep, M), bhy_adjusted(p_all, p_dep, M)
        b["rows"][M] = {"bonferroni": bon, "holm": hol, "bhy": bh,
                        "haircut_bonferroni": haircut(bon), "haircut_holm": haircut(hol), "haircut_bhy": haircut(bh)}
    res = {"grid": a, "ledger": b}
    L = [f"# Multiple-testing corrections for the combined book - {date.today()}", "",
         "Audit (no trial). (a) data snooping over the 144-configuration construction grid of #380 against IHSG; (b) the deployed",
         "Sharpe against the desk's whole ledger (Harvey-Liu-Zhu haircut).", "",
         f"## (a) Hansen SPA and Romano-Wolf, {a['K']} configurations, {a['n']} sessions, benchmark COMPOSITE, stationary bootstrap (block {BLOCK}, B {B})", "",
         "| SPA p-value | configurations beating IHSG (Romano-Wolf, FWER 5 %) | deployed t | deployed survives RW | deployed excess vs IHSG /yr |",
         "|---|---|---|---|---|",
         f"| **{a['spa_p']:.3f}** | {a['rw_rejected']} of {a['K']} | {a['deployed_t']:.2f} | {'yes' if a['deployed_rejected'] else 'no'} | {a['deployed_excess_ann'] * 100:+.1f} % |", "",
         f"## (b) Harvey-Liu-Zhu haircut, deployed Sharpe {SHARPE_DEP} over {YEARS} years (t {t_dep:.2f}, single-test p {p_dep:.1e})", "",
         f"Ledger p-value population: {len(sh):,} stored arm Sharpes converted at {YEARS} years.", "",
         "| effective tests M | Bonferroni p | Holm p | BHY p | haircut Sharpe (Bonf / Holm / BHY) |", "|---|---|---|---|---|"]
    for M, r in b["rows"].items():
        L.append(f"| {M} | {r['bonferroni']:.4f} | {r['holm']:.4f} | {r['bhy']:.4f} | {r['haircut_bonferroni']:.2f} / {r['haircut_holm']:.2f} / {r['haircut_bhy']:.2f} |")
    L += ["", "Reading against #380: the ledger DSR (0.23 at N 1,007) and this haircut (Sharpe 1.45-1.74 still significant at M 1,019)",
          "disagree because of the NULL they assume. The DSR takes the ledger's observed Sharpe spread (sd 0.78) as pure noise - very",
          "conservative, since many arms are variants of genuinely good books; the haircut takes the theoretical noise of a 4.7-year",
          "Sharpe (sd 1/sqrt(4.7) = 0.46). The truth lies between. The bootstrap t in (a) (4.60, autocorrelation-robust) is close to",
          "the iid t (4.79), so serial dependence does not rescue the pessimistic reading. Neither test can say whether 2022-26, a",
          "sample dominated by 2025, is representative of the next five years: that is not a multiple-testing question.",
          "", "Limits: (a) holds the signal rules fixed, so it only tests the construction search; (b) treats the deployed daily Sharpe",
          "as normal and independent (daily IDX returns are fat-tailed and autocorrelated, which inflates t) and converts every",
          "ledger arm at the same 4.7 years; the effective M is unknown and is shown as a range. The haircut Sharpe is the number",
          "to plan with only in the sense of 'what the evidence still supports', not a forecast."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_MULTIPLE_TESTING_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(),
                                  params={"trials": [], "kind": "audit", "bootstrap": {"B": B, "block": BLOCK, "seed": SEED},
                                          "years": YEARS, "m_grid": list(M_GRID), "sources": [348, 380]},
                                  summary=common.plain(res), names=[], report_path=out,
                                  note="SPA / Romano-Wolf on the construction grid; Harvey-Liu-Zhu haircut against the ledger; no trial")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
