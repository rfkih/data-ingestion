"""The horizons: intraday ones count session minutes on the trading grid, daily ones count trading days."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Horizon:
    key: str
    kind: str           # intraday | daily
    steps: int          # minutes on the session grid, or trading days
    label: str          # what the phone says
    basis: str = "abs"  # abs = the price itself; excess = return over the COMPOSITE (the 20d+ horizons: selection, not the market)


HORIZONS: dict[str, Horizon] = {h.key: h for h in (
    Horizon("1m", "intraday", 1, "1 menit"),
    Horizon("10m", "intraday", 10, "10 menit"),
    Horizon("30m", "intraday", 30, "30 menit"),
    Horizon("60m", "intraday", 60, "1 jam"),
    Horizon("1d", "daily", 1, "1 hari bursa"),
    Horizon("5d", "daily", 5, "1 minggu (5 hari bursa)"),
    Horizon("20d", "daily", 20, "1 bulan (20 hari bursa)", "excess"),
    Horizon("60d", "daily", 60, "3 bulan (60 hari bursa)", "excess"),
    Horizon("120d", "daily", 120, "6 bulan (120 hari bursa)", "excess"),
    Horizon("250d", "daily", 250, "1 tahun (250 hari bursa)", "excess"),
)}
INTRADAY = [h for h in HORIZONS.values() if h.kind == "intraday"]
DAILY = [h for h in HORIZONS.values() if h.kind == "daily"]
TASKS = ("dir", "ret")


def of_kind(kind: str) -> list[Horizon]:
    if kind == "all":
        return list(HORIZONS.values())
    return [h for h in HORIZONS.values() if h.kind == kind]
