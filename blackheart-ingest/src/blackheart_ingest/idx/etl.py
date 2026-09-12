"""Pure transformations bronze-row → silver-row. No I/O, no clock, no network.

Everything a job writes is computed here from the archived payload plus the
few facts it looks up (prior close, listed shares). Keeping this module pure
is what makes ``idx replay --from-bronze`` reproduce silver byte-for-byte.

Known feed defects handled (see spec §3a / §12):
* ``OpenPrice`` and ``FirstTrade`` both 0 → open is NULL (``open_missing``),
  not fabricated. Happened 2020-03-13..2020-09-04 when IDX had no pre-opening.
* ``Previous`` ≠ prior close → corporate action (split / reverse / rights /
  bonus). IDX resets the reference price on the ex-date; cash dividends do not.
* Weekend dates are never requested, so the 2021-05-22 phantom row cannot enter.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

ADJ_TOL = 0.005          # |Previous/prior_close - 1| above this = corporate action
SHARES_MATCH_TOL = 0.02  # price factor vs 1/share-ratio agreement for an exact split


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s[:10])


def _num(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v))
    except Exception:
        return None
    return d


def _pos(v: Any) -> Decimal | None:
    """Numeric or None; zero/negative → None (IDX writes 0 for 'not recorded')."""
    d = _num(v)
    return d if d is not None and d > 0 else None


def _int(v: Any) -> int | None:
    d = _num(v)
    return int(d) if d is not None else None


def _code(v: Any) -> str:
    return (v or "").strip().upper()


# ---------------------------------------------------------------------------
# Ringkasan Saham (GetStockSummary / GetTradingInfoSS rows)
# ---------------------------------------------------------------------------

def summary_row(r: dict[str, Any], fetched_at: datetime, bronze_id: int | None) -> dict[str, Any] | None:
    """One ``idx.daily_summary`` row from one payload row; None if unusable."""
    code = _code(r.get("StockCode"))
    d = parse_date(r.get("Date"))
    if not code or d is None:
        return None
    return {
        "trade_date": d, "code": code, "name": (r.get("StockName") or "").strip() or None,
        "remarks": r.get("Remarks"),
        "previous": _pos(r.get("Previous")), "open": _pos(r.get("OpenPrice")),
        "first_trade": _pos(r.get("FirstTrade")), "high": _pos(r.get("High")), "low": _pos(r.get("Low")),
        "close": _pos(r.get("Close")), "change": _num(r.get("Change")),
        "volume": _int(r.get("Volume")), "value": _int(r.get("Value")), "frequency": _int(r.get("Frequency")),
        "index_individual": _num(r.get("IndexIndividual")),
        "bid": _pos(r.get("Bid")), "bid_volume": _int(r.get("BidVolume")),
        "offer": _pos(r.get("Offer")), "offer_volume": _int(r.get("OfferVolume")),
        "listed_shares": _int(r.get("ListedShares")), "tradeable_shares": _int(r.get("TradebleShares")),
        "weight_for_index": _int(r.get("WeightForIndex")),
        "foreign_buy": _int(r.get("ForeignBuy")), "foreign_sell": _int(r.get("ForeignSell")),
        "delisting_date": parse_date(r.get("DelistingDate")) if r.get("DelistingDate") else None,
        "nonreg_volume": _int(r.get("NonRegularVolume")), "nonreg_value": _int(r.get("NonRegularValue")),
        "nonreg_frequency": _int(r.get("NonRegularFrequency")),
        "source_id": _int(r.get("IDStockSummary")), "bronze_id": bronze_id, "fetched_at": fetched_at,
    }


def summary_rows(rows: list[dict[str, Any]], fetched_at: datetime, bronze_id: int | None) -> list[dict[str, Any]]:
    out: dict[tuple[date, str], dict[str, Any]] = {}
    for r in rows:
        s = summary_row(r, fetched_at, bronze_id)
        if s is not None:
            out[(s["trade_date"], s["code"])] = s          # last wins on duplicates
    return [out[k] for k in sorted(out)]


def bar_row(s: dict[str, Any]) -> dict[str, Any] | None:
    """``idx.bar`` raw row from a summary row. None when there is no usable close."""
    close = s["close"]
    if close is None:
        return None
    flags: list[str] = []
    open_ = s["open"] if s["open"] is not None else s["first_trade"]
    open_missing = open_ is None
    if open_missing:
        flags.append("open_missing")
    high, low = s["high"], s["low"]
    if high is None or low is None or high <= 0 or low <= 0:
        high, low = close, close
        flags.append("hl_missing")
    if not s["volume"]:
        flags.append("no_trade")
    if open_ is not None and (high < max(open_, close) or low > min(open_, close)):
        flags.append("ohlc_inconsistent")
    return {
        "code": s["code"], "trade_date": s["trade_date"], "source": "idx", "basis": "split_only",
        "open": open_, "high": high, "low": low, "close": close,
        "volume": s["volume"], "value": s["value"], "open_missing": open_missing, "quality_flags": flags,
    }


def previous_reset(prior_close: Decimal | None, previous: Decimal | None) -> Decimal | None:
    """Price factor Previous/prior_close when it signals a corporate action, else None."""
    if not prior_close or not previous or prior_close <= 0 or previous <= 0:
        return None
    ratio = previous / prior_close
    if abs(ratio - 1) <= Decimal(str(ADJ_TOL)):
        return None
    return ratio


def classify_action(price_factor: Decimal, shares_before: int | None, shares_after: int | None) -> tuple[str, Decimal]:
    """(kind, factor). Uses the exact share ratio when it agrees with the price factor."""
    if shares_before and shares_after and shares_before > 0 and shares_after > 0:
        share_ratio = Decimal(shares_after) / Decimal(shares_before)
        if share_ratio != 1:
            implied = 1 / share_ratio
            if abs(implied / price_factor - 1) <= Decimal(str(SHARES_MATCH_TOL)):
                kind = "split" if share_ratio > 1 else "reverse_split"
                return kind, implied
    if price_factor < 1:
        return "rights_or_bonus", price_factor
    return "previous_reset", price_factor


# ---------------------------------------------------------------------------
# Daftar Saham (GetSecuritiesStock rows)
# ---------------------------------------------------------------------------

def listing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        code = _code(r.get("Code"))
        if not code:
            continue
        out[code] = {
            "code": code, "name": (r.get("Name") or "").strip() or None,
            "listing_date": parse_date(r.get("ListingDate")),
            "board": (r.get("ListingBoard") or "").strip() or None,
            "listed_shares": _int(r.get("Shares")),
        }
    return [out[k] for k in sorted(out)]


# ---------------------------------------------------------------------------
# Ringkasan Indeks (GetIndexSummary rows)
# ---------------------------------------------------------------------------

def index_rows(rows: list[dict[str, Any]], fetched_at: datetime, bronze_id: int | None) -> list[dict[str, Any]]:
    out: dict[tuple[date, str], dict[str, Any]] = {}
    for r in rows:
        code = _code(r.get("IndexCode"))
        d = parse_date(r.get("Date"))
        if not code or d is None:
            continue
        out[(d, code)] = {
            "trade_date": d, "index_code": code,
            "previous": _pos(r.get("Previous")), "open": None,
            "high": _pos(r.get("Highest")), "low": _pos(r.get("Lowest")), "close": _pos(r.get("Close")),
            "volume": _int(r.get("Volume")), "value": _int(r.get("Value")),
            "bronze_id": bronze_id, "fetched_at": fetched_at,
        }
    return [out[k] for k in sorted(out)]
