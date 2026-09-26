# ruff: noqa: RUF001  - display copy: the design uses the typographic minus, times, en dash and ≥
"""What the Strategies page says about each strategy - the reviewed prose, keyed by the REGISTRY key (registry.py is the one
catalog; this is its long-form half). Performance figures are NEVER typed here: a headline points at where the number is
stored (``idx.strategy_state`` for the scorecard entries, or a path inside a study summary), and the page reads it.

Per entry:
  family      the page's family: value | trend | event | ml | overlay
  status      optional override when no book says it (a watch that runs without a book, a closed family)
  one/what    the one-liner and the paragraph on top of the Overview
  rules       the rule as numbered steps
  how         (label, value) facts: universe, signal time, entry, exit, holding, tickets
  detail      (heading, paragraph) sections: the idea, entry, exit, sizing and risk, when it struggles
  research    the studies behind it, newest first on the page: study id (dates come from idx.study.run_at), title, what was
              tested, what was found, verdict (Adopted | Rejected | Inconclusive | Running), n. ``found`` and ``n`` are
              templates: every result figure is a {placeholder} whose spec in ``figs`` points into that study's stored
              summary (study_figures.py), so a re-run study updates the page and nothing here is a typed result. An entry
              with no stored study carries no figures at all. The verdict is the desk's decision on the study, kept here.
  figs        page-level figures for what / how / detail: S(study, spec) from a stored study, LIVE(name) counted now
  findings    option key -> research title, the study the Options tab quotes next to that setting
  headline    where the list's backtest figure comes from
  model       the training history source: {'kind': 'ml_model', 'horizon', 'task'} or {'kind': 'agent_model'}
  backtest    the study whose imported round trips feed the Results tab (idx.strategy_backtest_trade)
  sleeve      the combined book's sleeve key when the strategy is one of its three
  fills       how the backtest priced fills
"""
from __future__ import annotations

from typing import Any

from blackheart_ingest.idx.study_figures import COUNT, DIFF, LEN, LIVE, PCT, TEXT, YEAR, S, V

PAGES: dict[str, dict[str, Any]] = {
    # ---------------------------------------------------------------------------------------------------------- live
    "gapfade": {
        "family": "event", "sleeve": "gap",
        "one": "Buys liquid names that open 7 % or more below the previous close and sells them into the same close.",
        "what": "At the open it looks for main-board names trading at least Rp 5 bn a day that open 7 % or more under the previous "
                "close. The deepest gaps are bought at the open and every position is sold before the close the same day.",
        "rules": ["At 09:00, list main-board names with a 60-day value of at least Rp 5 bn opening 7 % or more below the previous close.",
                  "Take the deepest gaps first, at most five a day.",
                  "Buy at the open plus one tick.",
                  "Sell at 15:50, before the closing auction."],
        "how": [("Universe", "Main board, 60-day value ≥ Rp 5 bn"), ("Signal", "09:00 WIB"), ("Entry", "09:00–09:05, the open plus one tick"),
                ("Exit", "15:50 the same day"), ("Holding", "Same day"), ("Tickets", "Up to 5 per day")],
        "detail": [("The idea", "A large opening gap down in a liquid name is often an overreaction to overnight news that the session "
                                "partly takes back."),
                   ("Entry", "Only the first trade of the day counts - the pre-opening auction price is not what a retail order gets. "
                             "The five deepest gaps of the morning fill the slots."),
                   ("Exit", "Everything is sold into the same close. Exits at targets, stops and the next open were all tested and "
                            "none beat selling at the close."),
                   ("Sizing and risk", "10 % of NAV per trade in the combined portfolio. All trades are intraday, so the strategy "
                                       "carries no overnight risk. As deployed, the sleeve alone earns {lc} %/yr, Sharpe {ls}, max "
                                       "DD {ld} %; without 2025, {lx} %/yr (#348)."),
                   ("When it struggles", "Days when the gap is real news - a rights issue, a bad report - and the name keeps falling. "
                                         "Most of the historical events are from 2025–26, so the record rests on one regime.")],
        "figs": {"lc": S(348, PCT("gap_only/cagr", 1, sign=True)), "ls": S(348, V("gap_only/sharpe", 2)),
                 "ld": S(348, PCT("gap_only/mdd", 0)), "lx": S(348, PCT("gap_only/cagr_ex2025", 1, sign=True))},
        "research": [
            {"study": 77, "title": "The rule itself", "tested": "Buying opening gaps of −3 % to −10 %, sold at the close, 2020–2026 IDX opens.",
             "found": "The t-statistic of the −5 % and −7 % cuts is {t5} and {t7}, just under the bar of 3. A boundary result, re-read as "
                      "events accumulate.",
             "figs": {"t5": V("arms/g5/t", 2), "t7": V("arms/g7/t", 2), "n": LEN("arms")},
             "verdict": "Adopted", "n": "{n} cuts"},
            {"study": 86, "title": "Exits other than the close", "tested": "Targets, stops and holding to the next open.",
             "found": "{beat} of {exits} beat selling at the close. A +2 % target lifts the hit rate from {hit_c} % to {hit_t} %, but a +3 % "
                      "target cuts the mean from +{mean_c} to +{mean_t} bps.",
             "figs": {"beat": COUNT("arms", ("not_prefix", "no"), "verdict"), "exits": COUNT("arms", ("truthy",), "verdict"),
                      "hit_c": PCT("arms/close/hit", 0), "hit_t": PCT("arms/tp2/hit", 0),
                      "mean_c": V("arms/close/mean_bps", 0), "mean_t": V("arms/tp3/mean_bps", 0), "n": V("desc/events", 0)},
             "verdict": "Rejected", "n": "{n} events"},
            {"study": 89, "title": "Tuning the threshold", "tested": "Other gap depths, slot counts and liquidity floors.",
             "found": "{passed} of {arms} variants passed the bar; the deployed setting stays.",
             "figs": {"passed": LEN("verdict"), "arms": LEN("arms")}, "verdict": "Rejected", "n": "{arms} variants"},
            {"study": 87, "title": "A longer history", "tested": "Whether Yahoo opens can extend the record back to 2008.",
             "found": "Only from {first}: before it, Yahoo's open equals the close on too many days to measure a gap.",
             "figs": {"first": YEAR("quality/admitted_years/0"), "last": YEAR("quality/admitted_years/-1")},
             "verdict": "Inconclusive", "n": "{first}–{last}"},
            {"study": 88, "title": "Fading gap-ups", "tested": "Selling into opening gaps up of +3 % and more.",
             "found": "{follow} of {arms} arms worth a follow-up; not a rule yet.",
             "figs": {"follow": LEN("verdict"), "arms": LEN("arms")}, "verdict": "Inconclusive", "n": "{arms} arms"},
        ],
        "findings": {"per_day": "Tuning the threshold", "size": "Tuning the threshold"},
        "headline": {"state": "gapfade"},
        "backtest": {"study": 348, "file": "gap_only",
                     "config": "As deployed: Rp 20 M book, 10 % of NAV per gap, up to 5 a day, 30 % cash floor (study #348)."},
        "fills": "The open plus one tick at entry, the close less one tick at exit; Stockbit fees.",
    },
    "trend_small": {
        "family": "trend", "sleeve": "trend",
        "one": "Buys small caps closing at a 60-day high on heavy volume above their 200-day average; trails a 10 % stop.",
        "what": "Watches the liquid small caps. A name that closes at its 60-day high, above its 200-day average, on at least 1.5 times "
                "its usual volume is bought; it is held until it closes 10 % below its highest close since entry.",
        "rules": ["After the close, find small caps at a 60-day high and above their 200-day average.",
                  "Require volume at least 1.5 times the 20-day median.",
                  "Buy at the next close, strongest volume first.",
                  "Sell when the close falls 10 % below the peak close since entry."],
        "how": [("Universe", "Liquid tier minus blue chips (small tier)"), ("Signal", "Nightly plan after the close"),
                ("Entry", "Next close"), ("Exit", "10 % trailing stop"), ("Holding", "About 25 sessions"), ("Slots", "10 in its own book")],
        "detail": [("The idea", "Small caps that break out on volume tend to keep trending for weeks; they are thinly covered and slow to reprice."),
                   ("Entry", "The breakout close is the signal; the fill belongs to the next close. A fill one session late costs a "
                             "lot: the same rule filled a day late falls from Sharpe {sh_ref} to {sh_late}."),
                   ("Exit", "A 10 % trailing stop from the peak close. Thirty other exits were tested; none beat it."),
                   ("Sizing and risk", "5 % of NAV per trade in the combined portfolio, one tenth of its own book. The regime gate "
                                       "stops new entries while the IDX Composite is under its 200-day average. As deployed, the "
                                       "sleeve alone earns {lc} %/yr, Sharpe {ls}, max DD {ld} %; without 2025 only {lx} %/yr - "
                                       "most of its return came in one year (#348)."),
                   ("When it struggles", "Choppy markets, when breakouts fail - {fail5} % of volume breakouts are back inside their base "
                                         "within 5 days. The hit rate is about {hit} %; a few long trends carry the result.")],
        "figs": {"sh_ref": S(65, V("ref/sharpe", 2)), "sh_late": S(65, V("V5/late/ref/sharpe", 2)),
                 "lc": S(348, PCT("trend_only/cagr", 1, sign=True)), "ls": S(348, V("trend_only/sharpe", 2)),
                 "ld": S(348, PCT("trend_only/mdd", 0)), "lx": S(348, PCT("trend_only/cagr_ex2025", 1, sign=True)),
                 "fail5": S(130, PCT("primary/LIQ/fail5", 0)), "hit": S(23, PCT("results/small/hit", 0))},
        "research": [
            {"study": 22, "title": "Trend following with trailing exits", "tested": "Ten breakout and exit rules, 2020–2026.",
             "found": "The 60-day high with a 10 % trail on the liquid tier: hit rate {hit} %, payoff {payoff}, {avg} % net per trade. "
                      "{cand} of {arms} arms cleared every bar on its own.",
             "figs": {"hit": PCT("results/hi60|trail10|LIQ/hit", 0), "payoff": V("results/hi60|trail10|LIQ/payoff", 1),
                      "avg": PCT("results/hi60|trail10|LIQ/avg_net", 1, sign=True), "cand": V("candidates", 0), "arms": LEN("results")},
             "verdict": "Adopted", "n": "{arms} arms"},
            {"study": 23, "title": "Robustness", "tested": "Neighbouring windows, volume multiples and trails.",
             "found": "{robust} of its seven neighbours hold, so on the corrected data (2026-09-26 re-run) the lead rule is fragile by "
                      "this study's own test - it was robust on the old data. On small caps the rule earns Sharpe {real}; random entries "
                      "with the same exit on the liquid tier earn {rnd}.",
             "figs": {"robust": V("robust_n", 0), "arms": LEN("verdicts"), "real": V("results/small/sharpe", 2),
                      "rnd": V(("results", "random+trail10 LIQ", "sharpe"), 2)},
             "verdict": "Inconclusive", "n": "7 neighbours"},
            {"study": 46, "title": "2005–2019 on survivors", "tested": "The same rule on the names Yahoo still carries.",
             "found": "On small caps {cagr} % a year against {jkse} % for the IDX Composite, and it does not beat random entries - the "
                      "long-run base rate, well under the recent block.",
             "figs": {"cagr": PCT("results/small/cagr", 1, sign=True), "jkse": PCT("jkse/cagr", 1, sign=True), "years": LEN("jkse/years")},
             "verdict": "Inconclusive", "n": "{years} years"},
            {"study": 44, "title": "Other exits", "tested": "Thirty exit rules instead of the 10 % trail.",
             "found": "{better} of {exits} better by the money rule.",
             "figs": {"better": COUNT("better", ("not_prefix", "no")), "exits": LEN("better")}, "verdict": "Rejected", "n": "{exits} exits"},
            {"study": 63, "title": "Regime gate on entries", "tested": "No new entry while the IDX Composite is under its 200-day average.",
             "found": "Max drawdown {mdd_ref} % → {mdd_gate} %; the return gain appears only in bear blocks. Sharpe at the {pct}th "
                      "percentile of placebos.",
             "figs": {"mdd_ref": PCT("ref/mdd", 0), "mdd_gate": PCT("gate/mdd", 0), "pct": V("V4/percentile_of_real/sharpe", 0), "n": V("V4/n", 0)},
             "verdict": "Adopted", "n": "{n} placebos"},
            {"study": 91, "title": "Averaging down", "tested": "Adding to a position that falls.",
             "found": "{better} of {of} better; the portfolio worsens.", "figs": {"better": V("better", 0), "of": V("of", 0)},
             "verdict": "Rejected", "n": "{of} arms"},
            {"study": 58, "title": "An ML filter on entries", "tested": "Keep only breakouts the model scores well.",
             "found": "Filtered, small caps earn Sharpe {filtered} against {plain} plain - a gain below the +0.15 bar - and the drawdown "
                      "deepened ({mdd_p} % → {mdd_f} %).",
             "figs": {"plain": V("small/plain/sharpe", 2), "filtered": V("small/filtered/sharpe", 2),
                      "mdd_p": PCT("small/plain/mdd", 0), "mdd_f": PCT("small/filtered/mdd", 0), "years": LEN("small/per_year")},
             "verdict": "Rejected", "n": "{years} years"},
            {"study": 180, "title": "Breakout hold-or-fail model", "tested": "A model of whether a breakout holds, as a filter.",
             "found": "It re-learns the distance above the level (AUC {model} against {gap} for that alone) and adds nothing to the book.",
             "figs": {"model": V("pooled/model", 3), "gap": V("pooled/gap", 3), "n": V("pooled/n", 0)},
             "verdict": "Rejected", "n": "{n} breakouts"},
        ],
        "findings": {"regime_gate": "Regime gate on entries", "size": "Robustness"},
        "headline": {"state": "trend_small"},
        "backtest": {"study": 348, "file": "trend_only",
                     "config": "As deployed: Rp 20 M book, 5 % of NAV per name, regime gate, 30 % cash floor (study #348)."},
        "fills": "The closing offer at entry and the closing bid at exit, one session after the signal; Stockbit fees.",
    },
    "ml_rank": {
        "family": "ml", "sleeve": "ml", "model": {"kind": "ml_model", "horizon": "5d", "task": "ret"},
        "one": "A nightly model scores every name's next five days; a name is bought only after its price confirms the signal.",
        "what": "Every evening the 5-day model scores {universe} names. A name whose expected excess return pays at least twice its round-trip "
                "cost becomes a signal; it is bought only once the price confirms it, and sold when its score turns negative and a "
                "better name pays for the swap.",
        "rules": ["After the close, score every name with the 5-day model.",
                  "Signal a name when its smoothed expected excess pays at least twice its round trip.",
                  "Buy only after the price confirms: the four rules of ens4 each watch a level (+5 % or +8 % or +10 % within 10 "
                  "sessions, +8 % within 5) and each takes a quarter of the slot.",
                  "Sell when the score turns negative and a better name pays the swap, or after 60 sessions; with a stop-loss set, "
                  "also when a name trades that far under its entry price from 15:40 - sold in that same closing session."],
        "how": [("Universe", "{universe} names, 60-day value ≥ Rp 5 bn, price ≥ Rp 100"), ("Signal", "Nightly, after the daily model run"),
                ("Entry", "Intraday, when a confirmation level prints"), ("Exit", "Score swap or 60 sessions; stop-loss when set (see Options)"),
                ("Holding", "About 25 sessions"), ("Sizing", "10 % of NAV per name in the live combined portfolio, a quarter per confirmation rule")],
        "detail": [("The idea", "The model's accuracy is modest. The money comes from how the score is used: cost-aware "
                                "entries, a price confirmation, and letting winners run."),
                   ("Entry", "A signal alone is not a buy. Waiting for the price to rise +5 % within 10 sessions keeps the return "
                             "({confirm} %/yr against {base} %/yr without it) with half the trades and far less risk: Sharpe "
                             "{cs} against {bs}, max DD {cd} % against {bd} %."),
                   ("Exit", "Without confirmation every stop made the book worse, because it sold the dip of names that went on to "
                            "double. With confirmed entries it is the other way round: a stop at -5 % gives {s5c} %/yr, Sharpe {s5s}, "
                            "max DD {s5d} % against {s0c} %/yr, Sharpe {s0s}, max DD {s0d} % without (study #281), and inside the live "
                            "combined book {c5c} %/yr, Sharpe {c5s} against {c0c} %/yr, Sharpe {c0s} (#282). Selling in the SAME "
                            "closing session instead of the next one cuts the worst trade from {nx} % to {sd} % (#288); the desk "
                            "checks the stop from 15:40. Take-profits made it worse. Whether the stop is on is shown under Options."),
                   ("Sizing and risk", "10 % of NAV per name in the live book since 2026-09-26, shared across the four confirmation "
                                       "rules (a quarter each). The portfolio's cash floor is checked before each buy. As deployed, "
                                       "the sleeve alone earns {lc} %/yr, Sharpe {ls}, max DD {ld} %; without 2025, {lx} %/yr (#348)."),
                   ("When it struggles", "Market-wide sell-offs such as 2022, when rankings built on recent behaviour stop holding. "
                                         "No filter or overlay tested fixed the 2022 drawdown.")],
        "figs": {"universe": LIVE("ml_universe"), "confirm": S(160, PCT("wait_up5/cagr", 0, sign=True)),
                 "base": S(160, PCT("base/cagr", 0, sign=True)),
                 "cs": S(160, V("wait_up5/sharpe", 2)), "bs": S(160, V("base/sharpe", 2)),
                 "cd": S(160, PCT("wait_up5/mdd", 0)), "bd": S(160, PCT("base/mdd", 0)),
                 "s5c": S(281, PCT("arms/stop5/cagr", 1, sign=True)), "s5s": S(281, V("arms/stop5/sharpe", 2)),
                 "s5d": S(281, PCT("arms/stop5/mdd", 0)), "s0c": S(281, PCT("base/cagr", 1, sign=True)),
                 "s0s": S(281, V("base/sharpe", 2)), "s0d": S(281, PCT("base/mdd", 0)),
                 "c5c": S(282, PCT("arms/stop5/cagr", 1, sign=True)), "c5s": S(282, V("arms/stop5/sharpe", 2)),
                 "c0c": S(282, PCT("arms/none/cagr", 1, sign=True)), "c0s": S(282, V("arms/none/sharpe", 2)),
                 "nx": S(288, V("arms/nextclose_stop5/worst", 1, sign=True)), "sd": S(288, V("arms/same_stop5/worst", 1, sign=True)),
                 "lc": S(348, PCT("ml_only/cagr", 1, sign=True)), "ls": S(348, V("ml_only/sharpe", 2)), "ld": S(348, PCT("ml_only/mdd", 0)),
                 "lx": S(348, PCT("ml_only/cagr_ex2025", 1, sign=True))},
        "research": [
            {"study": 154, "title": "Cost-aware construction", "tested": "The same 5-day score used cost-aware instead of as fixed daily cohorts.",
             "found": "{cagr} %/yr, Sharpe {sharpe}, max DD {mdd} % for the cost-aware book; positive in {pos} of {years} years.",
             "figs": {"cagr": PCT("arms/e5|2|3|10/cagr", 1, sign=True), "sharpe": V("arms/e5|2|3|10/sharpe", 2),
                      "mdd": PCT("arms/e5|2|3|10/mdd", 0), "pos": V("arms/e5|2|3|10/years_pos", 0), "years": V("arms/e5|2|3|10/n_years", 0),
                      "trades": V("arms/e5|2|3|10/trades", 0)},
             "verdict": "Adopted", "n": "{trades} trades"},
            {"study": 159, "title": "Stops", "tested": "Price stops of 5–30 %, time stops and combinations, on the book without confirmation.",
             "found": "{worse} of {arms} stop rules are worse: without a confirmed entry a stop sells the dip of the names that go on "
                      "to double.",
             "figs": {"worse": COUNT("", ("prefix", "no"), "verdict"), "arms": COUNT("", ("truthy",), "verdict"), "trades": V("base/trades", 0)},
             "verdict": "Rejected", "n": "{trades} trades"},
            {"study": 160, "title": "Price confirmation", "tested": "Buy only after a +5 % move within 10 sessions; buying dips as the alternative.",
             "found": "{cagr} %/yr, Sharpe {sharpe}, max DD {mdd} %, hit rate {win} %. Dip entries were all worse.",
             "figs": {"cagr": PCT("wait_up5/cagr", 1, sign=True), "sharpe": V("wait_up5/sharpe", 2), "mdd": PCT("wait_up5/mdd", 0),
                      "win": PCT("wait_up5/win", 0), "trades": V("wait_up5/trades", 0)},
             "verdict": "Adopted", "n": "{trades} trades"},
            {"study": 162, "title": "Stops on the confirmed book", "tested": "Stops and trails on the single +5 % confirmation rule.",
             "found": "{better} of {arms} stop and trail rules pass the bar on the corrected data (stop -5 %: Sharpe {s5} against "
                      "{b0} without); the pattern was mixed, so the question was re-asked on the live rule set (study #281).",
             "figs": {"better": COUNT("arms", ("eq", "BETTER"), "verdict"), "arms": COUNT("arms", ("truthy",), "verdict"),
                      "s5": V("arms/stop5/sharpe", 2), "b0": V("arms/base/sharpe", 2), "trades": V("arms/base/trades", 0)},
             "verdict": "Inconclusive", "n": "{trades} trades"},
            {"study": 281, "title": "Exits on the live sleeve", "tested": "Fixed stops, trailing stops and take-profits on ens4, pre-registered, "
             "with neighbour, half-period, ex-2025 and placebo checks.",
             "found": "Stop -5 %: {s5c} %/yr, Sharpe {s5s}, max DD {s5d} % against {bc} %/yr, Sharpe {bs}, max DD {bd} % without; "
                      "{rec} of {arms} exits pass every check. Take-profits are all worse.",
             "figs": {"s5c": PCT("arms/stop5/cagr", 1, sign=True), "s5s": V("arms/stop5/sharpe", 2), "s5d": PCT("arms/stop5/mdd", 0),
                      "bc": PCT("base/cagr", 1, sign=True), "bs": V("base/sharpe", 2), "bd": PCT("base/mdd", 0),
                      "rec": LEN("recommended"), "arms": LEN("arms"), "trades": V("arms/stop5/trades", 0)},
             "verdict": "Adopted", "n": "{trades} trades"},
            {"study": 282, "title": "The stop inside the live book", "tested": "The live combined book (cash floor, trend and gap-fade "
             "sharing the cash) with ens4 at a quarter slot per rule, without a stop and with -5 % and -10 %.",
             "found": "Without a stop {c0} %/yr, Sharpe {s0}; stop -5 % {c5} %/yr, Sharpe {s5}; stop -10 % {c10} %/yr, Sharpe {s10}. "
                      "The single +5 % rule at a full slot makes {cr} %/yr: a quarter slot cannot buy the dearer names.",
             "figs": {"c0": PCT("arms/none/cagr", 1, sign=True), "s0": V("arms/none/sharpe", 2), "c5": PCT("arms/stop5/cagr", 1, sign=True),
                      "s5": V("arms/stop5/sharpe", 2), "c10": PCT("arms/stop10/cagr", 1, sign=True), "s10": V("arms/stop10/sharpe", 2),
                      "cr": PCT("reference_single/cagr", 1, sign=True)},
             "verdict": "Adopted", "n": "Rp 20 M book"},
            {"study": 164, "title": "Before 2020", "tested": "A price-only cousin of the model on 2009–19 survivors.",
             "found": "{cagr} %/yr for the base book; the edge lives in the IDX tape and fundamentals the older data lacks.",
             "figs": {"cagr": PCT("oos/base/cagr", 1, sign=True), "years": V("oos/base/n_years", 0)},
             "verdict": "Inconclusive", "n": "{years} years"},
            {"study": 173, "title": "Feature construction", "tested": "Cross-sectional ranks, sample weights, seed ensembles, lambdarank, smoothing.",
             "found": "{adopted} of {arms} adopted: accuracy moved, the money did not.",
             "figs": {"adopted": COUNT("verdict", ("truthy",), "adopt"), "arms": LEN("verdict")},
             "verdict": "Rejected", "n": "{arms} arms"},
            {"study": 175, "title": "Confirmation ensemble", "tested": "Four confirmation rules sharing the slot (ens4) against the single rule.",
             "found": "{cagr} %/yr, Sharpe {sharpe} and far less sensitive to the choice of rule (Sharpe range {rng} against {rng1} for a "
                      "single rule).",
             "figs": {"cagr": PCT("arms/ens4/cagr", 1, sign=True), "sharpe": V("arms/ens4/sharpe", 2), "rng": V("arms/ens4/loo_sharpe_range", 2),
                      "rng1": V("median_single/sharpe_range", 2), "rules": LEN("single")},
             "verdict": "Adopted", "n": "{rules} rules"},
            {"study": 176, "title": "Two-model order", "tested": "A lambdarank order gated by the regression model.",
             "found": "{better} of {arms} arms beat the regression's own order, but none clears the bar - every one draws down past the "
                      "limit - so the lambdarank family stays closed.",
             "figs": {"better": LEN("better"), "arms": LEN("arms")}, "verdict": "Rejected", "n": "{arms} arms"},
        ],
        "findings": {"confirm": "Confirmation ensemble", "margin": "Cost-aware construction", "max_hold": "Stops", "size": "Cost-aware construction",
                     "stop": "Exits on the live sleeve"},
        "headline": {"study": 288, "path": ["arms", "same_stop5"]},              # ens4 with the same-day stop, as deployed
        "backtest": {"study": 348, "file": "ml_only",
                     "config": "As deployed: Rp 20 M book, 10 % of NAV per name split over the four ens4 confirmation rules, same-day "
                               "stop -5 %, 30 % cash floor (study #348)."},
        "fills": "The closing offer on the day the confirmation level prints; the closing bid at exit (a stop: the bid at the close "
                 "that triggers it); Stockbit fees.",
    },
    "value_strict": {
        "family": "value",
        "one": "Holds the cheapest fifth of a strict quality pool on earnings, book and dividend yield; rebalanced each May.",
        "what": "A strict quality gate first - ROE at least 10 %, audited profit this year and last, positive operating cash flow, debt "
                "at most 1.5 times equity. Inside that pool the composite of earnings, book and dividend yield is ranked and the "
                "cheapest fifth is held, equal weight, for a year.",
        "rules": ["Keep liquid names that pass the quality gate (financials exempt from the debt test).",
                  "Rank the pool on earnings yield, book yield and dividend yield together.",
                  "Hold the cheapest fifth, equal weight.",
                  "Rebalance once a year, in May, after the annual reports."],
        "how": [("Universe", "Main and development boards, liquid"), ("Signal", "Each May, after annual reports"), ("Entry", "Rebalance ticket"),
                ("Exit", "Next May's rebalance"), ("Holding", "About a year"), ("Names", "About 10–12")],
        "detail": [("The idea", "Names cheap on several measures at once, and profitable, tend to outperform over a year. Cheap on one "
                                "measure alone is often cheap for a reason."),
                   ("Entry", "One rebalance a year. The screen is point in time: a report counts from its publication date."),
                   ("Exit", "Held to the next rebalance. A +100 % take-profit had too few events to learn from."),
                   ("Sizing and risk", "Equal weight across 10–12 names. Turnover is low, so costs weigh little."),
                   ("When it struggles", "Long stretches when growth or momentum leads; the 2023–26 half earned less than 2020–23.")],
        "research": [
            {"study": 66, "title": "Robustness scorecard", "tested": "Neighbouring pool cuts, placebo books, halves, costs ×1.5.",
             "found": "{verdict}: {npass} of {nb} neighbours pass, Sharpe at the {pct}th percentile of {placebo} random strict-pool books.",
             "figs": {"verdict": TEXT("S1/verdict"), "npass": V("S1/n_pass", 0), "nb": LEN("S1/neighbours"),
                      "pct": V("S1/placebo/pct/sharpe", 0), "placebo": V("S1/placebo/n", 0), "reb": LEN("S1/rebalances")},
             "verdict": "Adopted", "n": "{reb} rebalances"},
            {"study": 47, "title": "Eight-gate quality book", "tested": "A stricter Buffett-style gate as the list.",
             "found": "{passed} of {universe} names pass all {gates} gates; kept as a reading, not a separate book.",
             "figs": {"passed": V("passed", 0), "universe": V("universe", 0), "gates": LEN("fail_counts")},
             "verdict": "Inconclusive", "n": "{passed} names"},
            {"study": 93, "title": "Mixing with trend", "tested": "Value and trend weights from 0 to 100 %.",
             "found": "{robust} of {of} weightings robust; the surface is flat and the regime gate adds more than any reweighting.",
             "figs": {"robust": V("robust", 0), "of": V("of", 0)}, "verdict": "Inconclusive", "n": "{of} weights"},
            {"study": 181, "title": "As a sleeve next to the combined portfolio", "tested": "50–80 % of capital in the combined book, the rest in value.",
             "found": "Correlation {corr}: blending damps the drawdown but lowers the return; {passed} of {blends} pass every check.",
             "figs": {"corr": V("corr/0", 2, sign=True), "passed": LEN("passed"), "blends": LEN("verdict"), "arms": LEN("res")},
             "verdict": "Rejected", "n": "{arms} arms"},
        ],
        "findings": {"regime_exit": "Robustness scorecard", "take_profit": "Robustness scorecard", "max_names": "Eight-gate quality book"},
        "headline": {"state": "value_strict"},
        "fills": "The rebalance day's close; costs Stockbit fees.",
    },
    "ml_agent": {
        "family": "ml", "status": "paper", "model": {"kind": "agent_model"},
        "one": "A paper agent that trades the live tick feed with profit brackets and learns from every session.",
        "what": "Five times a session it looks at every name the tick feed carries and may buy up to three with a bracket - take-profit and "
                "stop - or hold for one, two or five sessions. After the close it learns from what every action would have paid for every "
                "name, and it trades only when its cautious estimate clears +0.3 % after costs.",
        "rules": ["At 09:15, 10:00, 11:00, 13:45 and 14:30, score every feed name for five brackets.",
                  "Take a name only when the pessimistic expected return clears +0.3 % after costs.",
                  "At most three new positions per decision and ten open, Rp 2 M each, on paper.",
                  "Exit at the bracket, or at the bid when the holding time runs out."],
        "how": [("Universe", "The {feed} names on the live tick feed"), ("Signal", "5 decision minutes a session"),
                ("Entry", "The offer at the decision minute"), ("Exit", "Take-profit, stop or time"),
                ("Holding", "Same day to 5 sessions"), ("Capital", "Rp 20 M, virtual")],
        "detail": [("The idea", "Five sessions of data are too few to train offline, so it trades forward on paper and every decision is "
                                "out of sample by construction."),
                   ("Learning", "The tape tells what every bracket would have paid for every name, not only the trades taken - about "
                                "{per_session} outcomes a session so far. Samples from one day move together, so their weight is discounted."),
                   ("Judgement", "After 20 sessions and 30 trades it is compared with a random agent that takes the same number of "
                                 "names at the same minutes; the rule was fixed before its first trade."),
                   ("When it struggles", "Spread and fees: an unconditional entry loses about {uncond} % a trade in the samples, so most "
                                         "of the time the right answer is no trade.")],
        "figs": {"feed": LIVE("feed_names"), "per_session": LIVE("agent_samples_per_session"), "uncond": LIVE("agent_uncond_ret")},
        "research": [
            {"study": None, "date": "2026-09-25", "title": "Thompson sampling", "tested": "Exploring with posterior draws, the first design.",
             "found": "In a walk-forward replay it lost more per trade than random names and filled every slot with an action seen for "
                      "one day. The replay was not stored as a study.",
             "verdict": "Rejected", "n": "–"},
            {"study": None, "date": "2026-09-25", "title": "Session-clustered uncertainty", "tested": "A pessimistic bound with the design effect of same-day samples, three sessions before an action is used.",
             "found": "No trade in the replay: no action's pessimistic bound cleared the bar. The replay was not stored as a study.",
             "verdict": "Adopted", "n": "–"},
        ],
        "findings": {},
        "headline": None,
        "fills": "The best offer at the decision minute, the bracket or the last bid; 0.10 % / 0.20 % fees.",
    },
    # ------------------------------------------------------------------------------------------------------ overlays
    "regime_gate": {
        "family": "overlay",
        "one": "No new entry while the IDX Composite closes below its 200-day average; held names keep their stops.",
        "what": "Places no trades of its own. On the trend and combined portfolios it stops new trend entries while the IDX Composite is "
                "under its 200-day average; positions already held keep their own exits.",
        "rules": ["Each evening compare the IDX Composite's close with its 200-day average.",
                  "Below it: the trend rule takes no new entry the next session.",
                  "Above it: entries resume."],
        "how": [("Applies to", "Trend entries in trend and combined portfolios"), ("Checked", "Nightly, before the plan"),
                ("Effect", "No new entry"), ("Trades", "None of its own")],
        "detail": [("The idea", "Breakouts fail more often in a falling market. Skipping entries there cuts the drawdown more than it "
                                "costs in return."),
                   ("What it is not", "It does not sell anything. The value book's regime option, which does sell to cash, is a "
                                      "different rule with its own evidence."),
                   ("When it struggles", "Fast V-shaped recoveries: the gate reopens only after the index is back over its average.")],
        "research": [
            {"study": 63, "title": "Validation", "tested": "The gate against shifted placebo regimes.",
             "found": "Max drawdown {mdd_ref} % → {mdd_gate} %; Sharpe at the {pct}th percentile of placebos. The return gain is not robust.",
             "figs": {"mdd_ref": PCT("ref/mdd", 0), "mdd_gate": PCT("gate/mdd", 0), "pct": V("V4/percentile_of_real/sharpe", 0), "n": V("V4/n", 0)},
             "verdict": "Adopted", "n": "{n} placebos"},
            {"study": 64, "title": "Catching the rebound", "tested": "Oversold re-entry rules to recover the rebound the gate misses.",
             "found": "The best of {rules} re-entry rules earns {best} %/yr against {gate} %/yr for the plain gate - inside the noise, so "
                      "none counts as recovering the rebound.",
             "figs": {"rules": LEN("res"), "best": PCT("res/os_ma50/cagr", 1, sign=True), "gate": PCT("gate/cagr", 1, sign=True)},
             "verdict": "Rejected", "n": "{rules} rules"},
            {"study": 65, "title": "A faster gate", "tested": "Allowing entries above the 50-day average as well.",
             "found": "{verdict}: it fails the placebo check (Sharpe at the {pct}th percentile).",
             "figs": {"verdict": TEXT("verdict"), "pct": V("V4/percentile_of_real/sharpe", 0), "n": LEN("V1/res")},
             "verdict": "Rejected", "n": "{n} regimes"},
        ],
        "findings": {"regime_gate": "Validation"},
        "headline": {"state": "regime_gate"},
    },
    "cash_floor": {
        "family": "overlay",
        "one": "Keeps part of the combined portfolio in cash: no new trade that would push the invested share past the floor.",
        "what": "Places no trades of its own. Before every buy in the combined portfolio it checks that the invested share stays under "
                "100 % minus the floor; a signal that would breach it waits.",
        "rules": ["Before a buy, add its cost to what is already invested.", "Refuse the buy if the invested share would pass 100 % minus the floor.",
                  "A refused ML watch stays open and can still fill if cash frees up."],
        "how": [("Applies to", "Every strategy in the combined portfolio"), ("Checked", "Every new buy"), ("Effect", "A buy waits"),
                ("Trades", "None of its own")],
        "detail": [("The idea", "The combined portfolio's drawdown came from being fully invested when all three strategies lost at "
                                "once. A floor keeps capacity back."),
                   ("When it struggles", "Strong markets where every signal pays: the floor leaves some of them unbought.")],
        "research": [
            {"study": 177, "title": "Allocation frontier", "tested": "Sizings and portfolio overlays on the combined engine.",
             "found": "{improving} of {overlays} overlays improves the book - the 30 % floor: max DD {mdd_base} % → {mdd_arm} % for {cost} pts of CAGR.",
             "figs": {"improving": LEN("improving_overlays"), "overlays": LEN("overlays"), "mdd_base": PCT("deployed/mdd", 0),
                      "mdd_arm": PCT("overlays/cash30/mdd", 0), "cost": DIFF("deployed/cagr", "overlays/cash30/cagr", 1, 100)},
             "verdict": "Adopted", "n": "{overlays} overlays"},
            {"study": 155, "title": "Risk overlays on ML", "tested": "Volatility targets and brakes on the ML book.",
             "found": "Nothing fixed the 2022 drawdown: the best overlay still fell {mdd} % at its worst.",
             "figs": {"mdd": PCT("arms/voltgt/mdd", 0, absval=True), "arms": LEN("arms")}, "verdict": "Rejected", "n": "{arms} arms"},
        ],
        "findings": {"cash_floor": "Allocation frontier"},
        "headline": {"study": 177, "base": ["deployed"], "arm": ["overlays", "cash30"]},
    },
    "regime_damper": {
        "family": "overlay",
        "one": "Two dampers for the value book: sell to cash below the 200-day average, and hold a cash buffer.",
        "what": "Places no trades of its own. On a value portfolio it can sell the book to cash while the IDX Composite is under its "
                "200-day average, and hold part of the book in cash at the monthly check.",
        "rules": ["Monthly, compare the IDX Composite with its 200-day average.", "Below it: sell the book to cash; above it: buy back.",
                  "Hold the set share of the book in cash."],
        "how": [("Applies to", "Value portfolios"), ("Checked", "Monthly"), ("Effect", "Sells to cash / holds cash"), ("Trades", "Exits only")],
        "detail": [("The idea", "Insurance, priced in return: it sat out the 2008 and 2020 crashes."),
                   ("Cost", "Part of the return in calm years; the buffer missed its return floor.")],
        "research": [
            {"study": None, "date": "2026-09-13", "title": "Index regime exit", "tested": "Selling the value book to cash below the 200-day average, 2008–2026.",
             "found": "Sat out the 2008 crash; costs part of the return in calm years. The run was not stored as a study.",
             "verdict": "Adopted", "n": "–"},
            {"study": None, "date": "2026-09-14", "title": "Cash buffer", "tested": "30 % cash, 50 % while stressed.",
             "found": "Robust as a damper; misses the return floor. The run was not stored as a study.", "verdict": "Inconclusive", "n": "–"},
        ],
        "findings": {"regime_exit": "Index regime exit", "cash_buffer": "Cash buffer"},
        "headline": None,
    },
    "ara_sell": {
        "family": "overlay", "status": "live",
        "one": "Sells a held name that touches its upper auto-rejection limit, at that price, instead of holding through it.",
        "what": "Places no trades of its own. During the session it watches every held name every two minutes; one that touches its upper "
                "limit raises an alert to sell there.",
        "rules": ["Every two minutes, check each held name against its upper auto-rejection price.", "On a touch, alert: sell at the limit."],
        "how": [("Applies to", "Every held name"), ("Checked", "Every 2 minutes in session"), ("Effect", "An alert to sell"), ("Trades", "None of its own")],
        "detail": [("The idea", "Holding through the ceiling costs {liq} bps on liquid names and {all} on all names, against selling at it; "
                                "holding beat selling only {pos} % of the time on liquid names."),
                   ("Scope", "Frozen by the operator on 23 Sep 2026: keep the watch and the alert, build nothing further.")],
        "figs": {"liq": S(101, V("reads/LIQ/H0/mean", 0, absval=True)), "all": S(101, V("reads/ALL/H0/mean", 0, absval=True)),
                 "pos": S(101, PCT("reads/LIQ/H0/p_pos", 0))},
        "research": [
            {"study": 101, "title": "Sell at the ceiling", "tested": "Selling at the ARA touch against holding 1, 5 or 20 sessions.",
             "found": "Selling wins in {win} of {years} years on liquid names; holding costs {liq}–{all} bps.",
             "figs": {"win": COUNT("reads/LIQ/H0/by_year", ("lt", 0), "mean"), "years": LEN("reads/LIQ/H0/by_year"),
                      "liq": V("reads/LIQ/H0/mean", 0, absval=True), "all": V("reads/ALL/H0/mean", 0, absval=True), "n": V("reads/LIQ/H0/n", 0)},
             "verdict": "Adopted", "n": "{n} touches"},
            {"study": 146, "title": "Next-day ARA model", "tested": "Ranking tomorrow's upper-limit locks.",
             "found": "AUC {auc} (placebo at the {pct}th percentile), but the top names are already locked and cannot be bought.",
             "figs": {"auc": V("placebo/real", 2), "pct": V("placebo/pct", 0), "years": LEN("by_year")},
             "verdict": "Inconclusive", "n": "{years} years"},
        ],
        "findings": {},
        "headline": None,
    },
    "exec_timing": {
        "family": "overlay", "status": "live",
        "one": "For a trade already decided, the order book says whether to rest at the bid or take the offer now.",
        "what": "Places no trades of its own. On the ticket screens it reads the live order book: a buy that waits for the book to lean "
                "to the bid filled {d1} and {d2} bps better than hitting the offer at once on the two sessions measured.",
        "rules": ["For each open ticket line, read queue imbalance and the microprice.", "Suggest resting at the bid when the book leans to it."],
        "how": [("Applies to", "Every ticket line"), ("Checked", "Live, on the ticket screen"), ("Effect", "Order placement"), ("Trades", "None of its own")],
        "detail": [("The idea", "Not a reason to trade: it improves the price of trades the portfolios take anyway.")],
        "figs": {"d1": S(99, V("S6/buy/by_day/2026-09-22/mean", 0)), "d2": S(99, V("S6/buy/by_day/2026-09-23/mean", 0))},
        "research": [
            {"study": 99, "title": "Where the edge survives costs", "tested": "Order-book signals as trades and as timing.",
             "found": "As timing only: {d1} and {d2} bps per buy decision better than an immediate fill; {cand} of {trials} arms survive costs.",
             "figs": {"d1": V("S6/buy/by_day/2026-09-22/mean", 0), "d2": V("S6/buy/by_day/2026-09-23/mean", 0),
                      "cand": LEN("verdict/candidates"), "trials": V("verdict/n_trials", 0), "days": LEN("desc/days")},
             "verdict": "Adopted", "n": "{days} sessions"},
            {"study": 74, "title": "Order-book signals", "tested": "Queue imbalance and trade flow over 1–5 minutes.",
             "found": "Real leads, never large enough to pay the spread as a trade: the median spread is {spread} bps.",
             "figs": {"spread": V("desc/median_spread_bps", 0), "names": V("desc/names", 0)},
             "verdict": "Inconclusive", "n": "{names} names"},
        ],
        "findings": {},
        "headline": None,
    },
    "combo_live": {
        "family": "ml",
        "one": "The live portfolio: gap-fade, trend and the ML ranking on one Rp 20 M book with a cash floor.",
        "what": "One cash pool runs three strategies at once. Each trade is sized as a share of the book's value, and a 30 % cash "
                "floor keeps part of it in cash. As deployed it earns {cagr} %/yr with Sharpe {sharpe} and a max drawdown of {mdd} % "
                "in a backtest over the same years its settings were chosen on; without 2025, {x25} %/yr. Read it as the best case.",
        "rules": ["Gap-fade: 10 % of NAV per gap, up to 5 a day, bought at the open and sold into the close.",
                  "Trend: 5 % of NAV per name, 60-day high on volume, 10 % trailing stop, no new entries under the regime gate.",
                  "ML: 10 % of NAV per name, a quarter for each of the four ens4 confirmation rules, same-day stop -5 %.",
                  "No buy that would take the invested share above 70 % (the cash floor)."],
        "how": [("Universe", "Each strategy's own: liquid main-board gaps, the small tier for trend, the model's liquid names for ML"),
                ("Capital", "Rp 20 M"), ("Sleeves", "Gap 10 % · trend 5 % · ML 10 % of NAV per trade"), ("Cash floor", "30 %"),
                ("Plan", "Nightly 21:10"), ("Intraday", "Session tick every minute: ML confirmations, the ML stop from 15:40, the gap "
                                                        "exit from 15:50"), ("Orders", "Live: draft tickets you execute; paper: filled at once")],
        "detail": [("Why these three", "They draw on different things: an overreaction at the open, momentum over weeks, and the "
                                       "model's ranking. Together the drawdown is shallower than the ML sleeve's alone ({ml_mdd} %)."),
                   ("Robustness", "Sharpe {h1} in the first half (2022 to April 2024) and {h2} in the second; without 2025, {x25} %/yr "
                                  "and Sharpe {sx25}. 2025 carries much of the result."),
                   ("Configuration", "The allocation was raised from 10/5/5 to 10/5/10 with the stop on 2026-09-26. The same engine with "
                                     "the old allocation and no stop earned {old} %/yr, Sharpe {olds} (#282)."),
                   ("When it struggles", "A market-wide sell-off hits the trend and ML sleeves together; the cash floor and the "
                                         "regime gate soften it but do not remove it."),
                   ("Reading the backtest", "In-sample: the allocation, the stop and the way the stop is executed were each chosen "
                                            "after seeing this same history, and 2025 alone returned {y25} %. Treat the figures as "
                                            "the best case, not a forecast. The live book has no record yet: judge it by its paper "
                                            "twin and its real fills, and set the loss that would stop it before it trades.")],
        "figs": {"y25": S(348, PCT("combined/by_year/2025", 0, sign=True)), "cagr": S(348, PCT("combined/cagr", 1, sign=True)), "sharpe": S(348, V("combined/sharpe", 2)),
                 "mdd": S(348, PCT("combined/mdd", 0)), "x25": S(348, PCT("combined/cagr_ex2025", 1, sign=True)),
                 "sx25": S(348, V("combined/sharpe_ex2025", 2)), "h1": S(348, V("combined/sharpe_h1", 2)),
                 "h2": S(348, V("combined/sharpe_h2", 2)), "ml_mdd": S(348, PCT("ml_only/mdd", 0)),
                 "old": S(282, PCT("arms/none/cagr", 1, sign=True)), "olds": S(282, V("arms/none/sharpe", 2))},
        "research": [
            {"study": 166, "title": "Three strategies on one book", "tested": "Gap-fade, trend and ML at 5 % of NAV each, one cash pool.",
             "found": "{cagr} %/yr, Sharpe {sharpe}, max DD {mdd} % for the three together, against {g} %, {t} % and {m} %/yr for "
                      "each alone on the same engine.",
             "figs": {"cagr": PCT("combined/cagr", 1, sign=True), "sharpe": V("combined/sharpe", 2), "mdd": PCT("combined/mdd", 0),
                      "g": PCT("gap_only/cagr", 1, sign=True), "t": PCT("trend_only/cagr", 1, sign=True), "m": PCT("ml_only/cagr", 1, sign=True),
                      "trades": V("combined/trades", 0)},
             "verdict": "Adopted", "n": "{trades} trades"},
            {"study": 282, "title": "The ML stop inside the book", "tested": "The live ens4 sleeve with and without a stop.",
             "found": "Without a stop {c0} %/yr, Sharpe {s0}; stop -5 % {c5} %/yr, Sharpe {s5}.",
             "figs": {"c0": PCT("arms/none/cagr", 1, sign=True), "s0": V("arms/none/sharpe", 2), "c5": PCT("arms/stop5/cagr", 1, sign=True),
                      "s5": V("arms/stop5/sharpe", 2)},
             "verdict": "Adopted", "n": "2 arms"},
            {"study": 348, "title": "As deployed", "tested": "Gap 10 % / trend 5 % / ML 10 % with the same-day stop, 30 % cash floor.",
             "found": "{cagr} %/yr, Sharpe {sharpe}, Sortino {sortino}, max DD {mdd} % over {sessions} sessions; {pos} of {months} "
                      "months positive; without 2025, {x25} %/yr.",
             "figs": {"cagr": PCT("combined/cagr", 1, sign=True), "sharpe": V("combined/sharpe", 2), "sortino": V("combined/sortino", 2),
                      "mdd": PCT("combined/mdd", 0), "sessions": V("combined/sessions", 0), "pos": V("combined/pos_months", 0),
                      "months": V("combined/n_months", 0), "x25": PCT("combined/cagr_ex2025", 1, sign=True), "trades": V("combined/trades", 0)},
             "verdict": "Adopted", "n": "{trades} trades"},
        ],
        "findings": {},
        "headline": {"study": 348, "path": ["combined"]},
        "backtest": {"study": 348, "file": "combined",
                     "config": "As deployed in live-fae554 (settings v2): Rp 20 M, gap 10 % / trend 5 % / ML 10 % of NAV per trade, ens4 "
                               "confirmation, same-day stop -5 %, 30 % cash floor (study #348)."},
        "fills": "Gap-fade: the open plus a tick, the close less a tick. Trend and ML: the closing offer at entry, the closing bid at "
                 "exit (an ML stop: the bid at the close that triggers it). Stockbit fees.",
    },
    # ------------------------------------------------------------------------------------------------------ research
    "combined_book": {
        "family": "value",
        "one": "Half the capital in the value book, half in the gated trend book.",
        "what": "A research configuration, not a portfolio: value and trend correlate weakly, so the pair has a shallower drawdown "
                "than either alone.",
        "rules": ["Hold the value strict composite with half the capital.", "Run the gated trend rule with the other half.", "Rebalance yearly."],
        "how": [("Universe", "As the two strategies"), ("Signal", "As the two strategies"), ("Entry", "–"), ("Exit", "–")],
        "detail": [("Status", "{robust} of {of} weightings are robust in both halves; the surface is flat. The live split is 67 / 33 "
                              "across two brokers.")],
        "figs": {"robust": S(93, V("robust", 0)), "of": S(93, V("of", 0))},
        "research": [
            {"study": 93, "title": "Weights", "tested": "Value and trend from 0 to 100 %.",
             "found": "{robust} of {of} weightings robust in both halves; the surface is flat (50/50 gated: {cagr} %/yr, max DD {mdd} %).",
             "figs": {"robust": V("robust", 0), "of": V("of", 0), "cagr": PCT("w50_50_gated/cagr", 1, sign=True), "mdd": PCT("w50_50_gated/mdd", 0)},
             "verdict": "Inconclusive", "n": "{of} weights"},
        ],
        "findings": {}, "headline": {"state": "combined_book"},
    },
    "trend_liq": {
        "family": "trend",
        "one": "The trend rule on the whole liquid tier instead of small caps - kept as the yardstick.",
        "what": "The same 60-day-high breakout with a 10 % trail, on every liquid name. It shows where the small-cap cut earns its drawdown.",
        "rules": ["As Trend on small caps, on the liquid tier."], "how": [("Universe", "Liquid tier"), ("Exit", "10 % trailing stop")],
        "detail": [("Status", "Reference only; fails the money rule on drawdown.")],
        "research": [{"study": 22, "title": "Liquid tier", "tested": "The trend rule on all liquid names.",
                      "found": "{cagr} %/yr, Sharpe {sharpe}, max DD {mdd} %.",
                      "figs": {"cagr": PCT("results/hi60|trail10|LIQ/cagr", 1, sign=True), "sharpe": V("results/hi60|trail10|LIQ/sharpe", 2),
                               "mdd": PCT("results/hi60|trail10|LIQ/mdd", 0), "n": V("results/hi60|trail10|LIQ/n", 0)},
                      "verdict": "Rejected", "n": "{n} trades"}],
        "findings": {}, "headline": {"state": "trend_liq"},
    },
    "fund_forecast": {
        "family": "ml",
        "one": "Forecasts the next financial report - profit up or down, and deterioration - before it is published.",
        "what": "A model of the next quarter's report from the last reports, prices and filings. Research only: whether it can be used as "
                "a risk filter is the next question.",
        "rules": ["On each quarter's end date, forecast the report due about 45 days later.", "Judge against a persistence baseline."],
        "how": [("Universe", "Names with parsed filings"), ("Signal", "Quarter ends"), ("Entry", "–"), ("Exit", "–")],
        "detail": [("Status", "Run on the full parsed filings after the report backlog drained (2026-09-26); research only.")],
        "research": [{"study": 179, "title": "Preliminary forecast", "tested": "Profit up YoY and deterioration, walk-forward 2022–2026.",
                      "found": "Profit up: AUC {up_m} against {up_n} for persistence, better in {up_w} of {years} years. Deterioration: {w_m} "
                               "against {w_n}, better in {w_w}.",
                      "figs": {"up_m": V("up/pooled/model", 2), "up_n": V("up/pooled/naive", 2), "up_w": V("up/wins", 0), "years": LEN("up/years"),
                               "w_m": V("worse/pooled/model", 2), "w_n": V("worse/pooled/naive", 2), "w_w": V("worse/wins", 0)},
                      "verdict": "Running", "n": "{years} years"}],
        "findings": {}, "headline": None,
    },
    # ------------------------------------------------------------------------------------------------------ closed
    "breakout_filter": {
        "family": "trend", "status": "closed",
        "one": "A model of whether a breakout holds, used to filter the trend rule. Closed.",
        "what": "Tested whether breakouts that will fail back into their base can be told apart on the breakout day.",
        "rules": ["Score each trend signal for holding 5 sessions.", "Drop or down-rank the weakest."], "how": [("Universe", "Trend signals")],
        "detail": [("Why it closed", "The model re-learned the distance above the breakout level; used in the book it added nothing.")],
        "research": [
            {"study": 130, "title": "Breakout outcomes", "tested": "Every volume breakout of a 60-day base.",
             "found": "{fail5} % back inside the base within 5 days; {above20} % still above it at 20 days.",
             "figs": {"fail5": PCT("primary/LIQ/fail5", 0), "above20": PCT("primary/LIQ/above20", 0), "n": V("primary/LIQ/n", 0)},
             "verdict": "Inconclusive", "n": "{n} breakouts"},
            {"study": 180, "title": "Hold-or-fail model", "tested": "LightGBM as a filter and a ranker.",
             "found": "AUC {model} against {gap} for one number, the distance above the level; no book improvement.",
             "figs": {"model": V("pooled/model", 3), "gap": V("pooled/gap", 3), "n": V("pooled/n", 0)},
             "verdict": "Rejected", "n": "{n} breakouts"},
        ],
        "findings": {}, "headline": None, "closed": "2026-09-25",
    },
    "close_vwap": {
        "family": "event", "status": "closed",
        "one": "Bought closes dumped below the day's VWAP, sold the next session. Closed.",
        "what": "Tested whether a close far below the day's volume-weighted price comes back overnight.",
        "rules": ["Find closes 3 % or more below the day's VWAP.", "Buy at the close, sell at the next open or close."], "how": [("Universe", "60-day value ≥ Rp 5 bn")],
        "detail": [("Why it closed", "The dumped names kept falling; what looked like a bounce was the market-wide overnight premium, "
                                     "smaller than the 0.5 % round trip.")],
        "research": [{"study": 182, "title": "Close against VWAP", "tested": "Two exits, neighbours and a reversal control.",
                      "found": "{o} %/yr sold at the next open and {c} %/yr at the next close, after costs.",
                      "figs": {"o": PCT("VW_O/cagr", 0), "c": PCT("VW_C/cagr", 0), "days": V("VW_O/days_active", 0)},
                      "verdict": "Rejected", "n": "{days} active days"}],
        "findings": {}, "headline": None, "closed": "2026-09-25",
    },
    "sideways": {
        "family": "trend", "status": "closed",
        "one": "Ways to trade names resting in a sideways range. Closed.",
        "what": "Tested buying the floor, the ceiling, the break and the dividend of sideways names.",
        "rules": ["Find names in a 120-day range.", "Trade the floor, the break or the yield."], "how": [("Universe", "Liquid names in a base")],
        "detail": [("Why it closed", "Every way to be paid was either already collected by the trend and value rules or a label artefact.")],
        "research": [
            {"study": 68, "title": "Range rules", "tested": "Range rules plus ML and DL models.",
             "found": "{passed} of {arms} arms pass the money rule.",
             "figs": {"passed": COUNT("money", ("not_prefix", "tested")), "arms": LEN("money"), "rules": LEN("rules")},
             "verdict": "Rejected", "n": "{rules} rules"},
            {"study": 69, "title": "How the range ends", "tested": "Breakout, dividend and direction models.",
             "found": "{passed} of {arms} arms pass; the direction model learned the label's construction.",
             "figs": {"passed": COUNT("money", ("not_prefix", "tested")), "arms": LEN("money"), "n": V("n_snapshots", 0)},
             "verdict": "Rejected", "n": "{n} snapshots"},
        ],
        "findings": {}, "headline": None, "closed": "2026-09-21",
    },
    "bandarmologi": {
        "family": "event", "status": "closed",
        "one": "Following broker accumulation. Closed.",
        "what": "Tested whether names the broker tape labels as accumulated rise afterwards.",
        "rules": ["Read the broker summary labels.", "Buy names labelled as accumulated."], "how": [("Universe", "Names with broker data")],
        "detail": [("Why it closed", "Accumulation precedes crashes as often as rises: it measures that something is happening, not the direction.")],
        "research": [
            {"study": 16, "title": "Follow the accumulation", "tested": "Foreign and broker accumulation screens.",
             "found": "{cand} of {arms}.", "figs": {"cand": V("candidates", 0), "arms": LEN("verdicts")}, "verdict": "Rejected", "n": "{arms} arms"},
            {"study": 18, "title": "Broker labels, 20 days", "tested": "Stockbit's accumulation labels.",
             "found": "{cand} of {arms}.", "figs": {"cand": V("candidates", 0), "arms": LEN("verdicts")}, "verdict": "Rejected", "n": "{arms} arms"},
            {"study": 19, "title": "Broker labels, 5 days", "tested": "The same on 5-day windows.",
             "found": "{cand} of {arms}.", "figs": {"cand": V("candidates", 0), "arms": LEN("verdicts")}, "verdict": "Rejected", "n": "{arms} arms"},
            {"study": 133, "title": "Both directions", "tested": "Accumulation before rises and before crashes.",
             "found": "The top tenth on 60-day OBV: lift {up} for a +50 % rise and {down} for a −30 % crash.",
             "figs": {"up": V("tiers/LIQ/features/obv60/top10/lift_rise50", 2), "down": V("tiers/LIQ/features/obv60/top10/lift_crash30", 2),
                      "n": V("panel/snapshots", 0)},
             "verdict": "Rejected", "n": "{n} snapshots"},
        ],
        "findings": {}, "headline": None, "closed": "2026-09-17",
    },
}
