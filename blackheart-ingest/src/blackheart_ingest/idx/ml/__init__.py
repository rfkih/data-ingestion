"""Self-learning prediction desk (operator, 2026-09-24: "continuous improving learning ... training setiap hari ... prediksi
arah pergerakan, prediksi harga ... 1 menit, 10 menit, 30 menit, 1 jam, 1 bulan, 1 tahun").

Every horizon gets two LightGBM models: ``dir`` (P(higher)) and ``ret`` (log return, turned into a price on the tick).
The loop (``loop.py``) retrains every day on everything that has matured, judges champion and challengers on the same
out-of-sample window, promotes the winner, predicts, and - the part that makes the number honest - fills in what
actually happened for every prediction and keeps a rolling scorecard per horizon against naive baselines.

    spec.py       the horizons and what they mean
    common.py     metrics without sklearn, tick rounding, params + perturbation, the registry, the promotion rule
    daily.py      the daily panel: bars, daily summary, index, macro, PIT fundamentals, broker flow, sentiment, consensus
    intraday.py   the minute panel off the tick feed (1-minute bars + book), on the session grid
    loop.py       train / predict / evaluate / scorecard entry points used by the scheduler, the CLI and the API

What the research already settled and this desk does not pretend otherwise: the intraday lead is real but smaller
than the spread (menus 28-33), a 24-day trade is path noise (ML-1), ARA is predictable but not buyable (ML-3), and the
loser-filter on PIT fundamentals works at a year (menus 10-11). Every prediction here is a measured forecast; nothing
in this package writes a ticket.
"""
