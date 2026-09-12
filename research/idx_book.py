#!/usr/bin/env python3
"""IDX manual position book — the operator is the broker adapter (execution v1).

Ledger lives in research-scratch/idx-book/ (gitignored):
  fills.csv      append-only: date,code,side,lots,price,fee_pct,note
  positions.csv  derived: code,lots,avg_price,cost_basis,realized_pnl
  cash.csv       optional deposits/withdrawals: date,amount,note

Conventions (IDX): 1 lot = 100 shares; prices in Rp; buy fee added to cost basis
(weighted-average cost), sell fee deducted from proceeds; realized P&L on sells
against average cost. Defaults: buy 0.15 %, sell 0.25 % (incl. 0.1 % final tax).

  python research/idx_book.py fill BBCA buy 10 6325 --date 2026-09-12
  python research/idx_book.py fill BBCA sell 4 6500 --date 2026-09-20 --fee 0.25
  python research/idx_book.py set BBCA 10 6325          # seed an existing position
  python research/idx_book.py cash 50000000 --note deposit
  python research/idx_book.py show                        # book + mark-to-market
"""
import argparse
import csv
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = os.path.join(ROOT, "research-scratch", "idx-book")
PRIMARY = os.path.join(ROOT, "research-scratch", "idx-primary")
LOT = 100
FEE = {"buy": 0.15, "sell": 0.25}   # percent


def _read(name, fields):
    p = os.path.join(BOOK, name)
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write(name, fields, rows):
    os.makedirs(BOOK, exist_ok=True)
    with open(os.path.join(BOOK, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


FILL_F = ["date", "code", "side", "lots", "price", "fee_pct", "note"]
POS_F = ["code", "lots", "avg_price", "cost_basis", "realized_pnl"]
CASH_F = ["date", "amount", "note"]


def rebuild_positions():
    """Positions are a pure function of fills (replayable)."""
    pos = {}
    for f in sorted(_read("fills.csv", FILL_F), key=lambda r: (r["date"], r["code"])):
        code, side = f["code"], f["side"].lower()
        lots, price, fee = int(f["lots"]), float(f["price"]), float(f["fee_pct"]) / 100
        p = pos.setdefault(code, {"lots": 0, "cost": 0.0, "realized": 0.0})
        gross = lots * LOT * price
        if side == "buy":
            p["cost"] += gross * (1 + fee)
            p["lots"] += lots
        elif side == "sell":
            if lots > p["lots"]:
                raise SystemExit("sell %d lots > held %d for %s on %s" % (lots, p["lots"], code, f["date"]))
            avg = p["cost"] / (p["lots"] * LOT) if p["lots"] else 0.0
            p["realized"] += gross * (1 - fee) - lots * LOT * avg
            p["cost"] -= lots * LOT * avg
            p["lots"] -= lots
        else:
            raise SystemExit("side must be buy/sell: %r" % f["side"])
    rows = []
    for code, p in sorted(pos.items()):
        avg = p["cost"] / (p["lots"] * LOT) if p["lots"] else 0.0
        rows.append({"code": code, "lots": p["lots"], "avg_price": "%.2f" % avg,
                     "cost_basis": "%.0f" % p["cost"], "realized_pnl": "%.0f" % p["realized"]})
    _write("positions.csv", POS_F, rows)
    return rows


def last_close(code):
    p = os.path.join(PRIMARY, code + ".csv")
    if not os.path.exists(p):
        return None, None
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return (rows[-1]["date"], float(rows[-1]["close"])) if rows else (None, None)


def show():
    rows = rebuild_positions()
    cash = sum(float(r["amount"]) for r in _read("cash.csv", CASH_F))
    for f in _read("fills.csv", FILL_F):
        gross = int(f["lots"]) * LOT * float(f["price"])
        fee = gross * float(f["fee_pct"]) / 100
        cash += -(gross + fee) if f["side"].lower() == "buy" else (gross - fee)
    print("%-6s %6s %10s %14s %14s %8s %14s %s" % ("code", "lots", "avg", "cost", "mkt value", "pnl%", "unreal pnl", "as of"))
    tot_cost = tot_mv = 0.0
    for r in rows:
        if int(r["lots"]) == 0:
            continue
        d, c = last_close(r["code"])
        cost = float(r["cost_basis"])
        mv = int(r["lots"]) * LOT * c if c else 0.0
        tot_cost += cost
        tot_mv += mv
        print("%-6s %6d %10.2f %14.0f %14.0f %7.2f%% %14.0f %s" % (
            r["code"], int(r["lots"]), float(r["avg_price"]), cost, mv,
            (mv / cost - 1) * 100 if cost and c else 0.0, mv - cost if c else 0.0, d or "no price"))
    realized = sum(float(r["realized_pnl"]) for r in rows)
    print("-- cost %.0f | market %.0f | unrealized %.0f | realized %.0f | cash %.0f | equity %.0f"
          % (tot_cost, tot_mv, tot_mv - tot_cost, realized, cash, cash + tot_mv))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fill")
    f.add_argument("code"); f.add_argument("side", choices=["buy", "sell"])
    f.add_argument("lots", type=int); f.add_argument("price", type=float)
    f.add_argument("--date", default=date.today().isoformat())
    f.add_argument("--fee", type=float, help="percent; default buy 0.15 / sell 0.25")
    f.add_argument("--note", default="")
    s = sub.add_parser("set", help="seed a held position (recorded as a buy at avg price, fee 0)")
    s.add_argument("code"); s.add_argument("lots", type=int); s.add_argument("avg_price", type=float)
    s.add_argument("--date", default=date.today().isoformat())
    c = sub.add_parser("cash"); c.add_argument("amount", type=float); c.add_argument("--note", default="")
    c.add_argument("--date", default=date.today().isoformat())
    sub.add_parser("show")
    a = ap.parse_args()
    if a.cmd == "fill":
        rows = _read("fills.csv", FILL_F)
        rows.append({"date": a.date, "code": a.code.upper(), "side": a.side, "lots": a.lots,
                     "price": "%g" % a.price, "fee_pct": "%g" % (a.fee if a.fee is not None else FEE[a.side]),
                     "note": a.note})
        _write("fills.csv", FILL_F, rows)
    elif a.cmd == "set":
        rows = _read("fills.csv", FILL_F)
        rows.append({"date": a.date, "code": a.code.upper(), "side": "buy", "lots": a.lots,
                     "price": "%g" % a.avg_price, "fee_pct": "0", "note": "seed existing position (avg incl. fees)"})
        _write("fills.csv", FILL_F, rows)
    elif a.cmd == "cash":
        rows = _read("cash.csv", CASH_F)
        rows.append({"date": a.date, "amount": "%g" % a.amount, "note": a.note})
        _write("cash.csv", CASH_F, rows)
    show()


if __name__ == "__main__":
    main()
