"""The one-tap fill's proposal (idx/fillmatch.py): which prints a line could have traded at, the price and size proposed,
and the confidence. Pure - no database, no writing: the fill itself still goes through ticket.fill_line."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from blackheart_ingest.idx import fillmatch

T = datetime(2026, 9, 23, 9, 30)


def pr(price, qty, minute=30):
    return {"price": Decimal(price), "qty": Decimal(qty), "at": T.replace(minute=minute)}


def line(side="buy", lots=20, limit=1000, filled=0, lid=7, code="BBRI"):
    return {"id": lid, "code": code, "side": side, "lots": Decimal(lots), "limit_price": Decimal(limit),
            "filled_lots": Decimal(filled), "status": "open"}


def test_eligible_respects_the_side_of_the_limit() -> None:
    prints = [pr(995, 100), pr(1000, 100), pr(1005, 100)]
    assert [p["price"] for p in fillmatch.eligible(prints, "buy", Decimal(1000))] == [Decimal(995), Decimal(1000)]
    assert [p["price"] for p in fillmatch.eligible(prints, "sell", Decimal(1000))] == [Decimal(1000), Decimal(1005)]
    assert fillmatch.eligible([], "buy", Decimal(1000)) == []


def test_full_fill_when_the_flow_dwarfs_the_line() -> None:
    # 20 lots = 2,000 shares; the market traded 100,000 inside the limit -> a full fill at the VWAP, high confidence
    out = fillmatch.propose(line(), [pr(995, 60_000), pr(1000, 40_000)])
    assert out["lots"] == Decimal(20) and out["confidence"] == "high"
    assert out["price"] == Decimal(1000)                     # VWAP 997 -> a buy snaps UP the tick (conservative), capped at the limit
    assert out["price"] <= out["limit_price"] and out["n_prints"] == 2 and out["volume"] == Decimal(100_000)
    assert out["first"] == T.replace(minute=30) and out["why"] is None


def test_medium_and_low_confidence_track_the_cover() -> None:
    med = fillmatch.propose(line(), [pr(1000, 6_000)])       # 3x the line's 2,000 shares -> full but only medium
    assert med["lots"] == Decimal(20) and med["confidence"] == "medium"
    low = fillmatch.propose(line(), [pr(1000, 1_500)])       # less than the line: propose what the flow could fill
    assert low["lots"] == Decimal(15) and low["confidence"] == "low"


def test_a_sell_never_proposes_below_its_limit() -> None:
    out = fillmatch.propose(line(side="sell", limit=1000), [pr(1000, 50_000), pr(1005, 10_000)])
    assert out["side"] == "sell" and out["lots"] == Decimal(20)
    assert out["price"] >= Decimal(1000)                     # a sell is never proposed under the limit it was worked at


def test_nothing_to_propose_is_said_plainly() -> None:
    none = fillmatch.propose(line(), [pr(1005, 99_000)])     # every print above a buy's limit
    assert none["lots"] == Decimal(0) and "no print at or below" in none["why"] and none["price"] is None
    crumbs = fillmatch.propose(line(), [pr(1000, 40)])       # less than one lot traded inside the limit
    assert crumbs["lots"] == Decimal(0) and "less than a lot" in crumbs["why"]
    done = fillmatch.propose(line(filled=20), [pr(1000, 99_000)])
    assert done["lots"] == Decimal(0) and done["why"] == "nothing left to fill"


def test_partial_line_proposes_only_what_is_left() -> None:
    out = fillmatch.propose(line(lots=20, filled=12), [pr(1000, 99_000)])
    assert out["remaining"] == Decimal(8) and out["lots"] == Decimal(8)


def test_render_is_readable() -> None:
    s = fillmatch.render({"ticket": 3, "book": "trend_live", "status": "issued", "date": T.date(),
                          "lines": [fillmatch.propose(line(), [pr(1000, 99_000)]), fillmatch.propose(line(lid=8, code="ERAA"), [])]})
    assert "ticket #3" in s and "BBRI" in s and "ERAA" in s and "no print at or below" in s


def test_only_an_issued_ticket_is_proposed_for(monkeypatch) -> None:
    """A draft is not at the broker yet and a closed or cancelled ticket is finished: neither may propose a fill."""
    from blackheart_ingest.idx import ticket as tk

    t = {"id": 5, "book": "trend_live", "status": "cancelled",
         "lines": [{"id": 1, "code": "IRSX", "side": "buy", "lots": Decimal(21), "limit_price": Decimal(456),
                    "filled_lots": Decimal(0), "status": "open"}]}
    monkeypatch.setattr(tk, "load", lambda conn, ticket_id=None, book=None: t)
    for status in ("cancelled", "draft", "closed"):
        t["status"] = status
        out = fillmatch.suggest(object(), 5, T.date())
        assert out["lines"] == [] and status in out["why"]
        assert status in fillmatch.render(out)
    t["status"] = "issued"
    monkeypatch.setattr(fillmatch, "prints_for", lambda conn, codes, d: {"IRSX": [pr(450, 99_000)]})
    out = fillmatch.suggest(object(), 5, T.date())
    assert len(out["lines"]) == 1 and out["lines"][0]["lots"] == Decimal(21)

