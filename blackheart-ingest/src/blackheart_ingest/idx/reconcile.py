"""Reconcile a book against the broker's portfolio export (Stockbit / IPOT / Ajaib have no API; they export CSV).

Pure parts: ``parse_csv`` (tolerant of the export's header names, ``;`` or ``,`` delimiters, and Indonesian ``1.234,56``
vs ``1,234.56`` numbers), ``diff`` (positions in the book vs at the broker: lots, average price). ``reconcile`` runs the
diff against ``idx.position`` and journals the outcome - it never changes the book: a difference is for the operator to
resolve with a fill or a correction, by hand, because the broker is the truth and the book is the record.

Header names recognised (case/space/underscore-insensitive; the first match wins): code = symbol | stock | kode |
saham | ticker | emiten | code; lots = lot | lots; shares = shares | qty | quantity | jumlah | volume | lembar | balance |
available; avg = avg | average | avg price | average price | harga rata | rata | avgprice | cost | harga beli.
Give a file with at least a code column and one of lots/shares; the average price is optional (then only lots are compared).
"""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg

from . import journal
from .card import _rows

LOT = 100
HEADERS = {
    "code": ("code", "symbol", "stock", "kode", "saham", "ticker", "emiten", "kodesaham", "stockcode"),
    "lots": ("lot", "lots", "jumlahlot", "totallot"),
    "shares": ("shares", "qty", "quantity", "jumlah", "volume", "lembar", "balance", "available", "jumlahsaham", "totalshares", "availablelot"),
    "avg": ("avg", "average", "avgprice", "averageprice", "hargarata", "hargaratarata", "rata", "rata2", "cost", "hargabeli", "avgcost", "averagecost"),
}
_THOUSANDS_DOT = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_THOUSANDS_COMMA = re.compile(r"^-?\d{1,3}(,\d{3})+$")


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def parse_number(s: Any) -> Decimal | None:
    """``"1.234,56"`` and ``"1,234.56"`` both -> 1234.56; ``"1.500"`` -> 1500 (Indonesian thousands), ``"3.5"`` -> 3.5;
    blanks, ``-`` and text -> None."""
    if s is None:
        return None
    if isinstance(s, int | float | Decimal):
        return Decimal(str(s))
    t = str(s).strip().replace("Rp", "").replace("IDR", "").replace(" ", "").replace(chr(0xA0), "")   # NBSP from spreadsheet exports
    if t in ("", "-", "n/a", "na"):
        return None
    if "." in t and "," in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        t = t.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in t:
        t = t.replace(",", "") if _THOUSANDS_COMMA.match(t) else t.replace(",", ".")
    elif "." in t and _THOUSANDS_DOT.match(t):
        t = t.replace(".", "")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def map_header(header: list[str]) -> dict[str, int]:
    """Column index per role; raises when no code column or neither lots nor shares is present."""
    norm = [_norm(h) for h in header]
    out: dict[str, int] = {}
    for role, names in HEADERS.items():
        for i, h in enumerate(norm):
            if h in names or any(h.startswith(n) and role != "code" for n in names if len(n) >= 4):
                out[role] = i
                break
    if "code" not in out:
        raise ValueError(f"no code column in header {header}")
    if "lots" not in out and "shares" not in out:
        raise ValueError(f"no lots/shares column in header {header}")
    return out


def parse_csv(text: str) -> list[dict[str, Any]]:
    """Broker export text -> rows {code, lots (Decimal), avg (Decimal | None)}; rows without a code or with zero lots are dropped."""
    text = text.lstrip(chr(0xFEFF))                                                  # UTF-8 BOM
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    # the header is the first row that maps; exports often start with account lines
    hi = None
    for i, r in enumerate(rows[:10]):
        try:
            cols = map_header(r)
            hi = i
            break
        except ValueError:
            continue
    if hi is None:
        raise ValueError(f"no usable header in the first rows: {rows[0]}")
    out: list[dict[str, Any]] = []
    for r in rows[hi + 1:]:
        if len(r) <= cols["code"]:
            continue
        code = re.sub(r"[^A-Z0-9]", "", r[cols["code"]].upper().split(".")[0])          # 'BBCA.JK' -> BBCA
        if not (3 <= len(code) <= 5) or not code[0].isalpha():
            continue
        lots = parse_number(r[cols["lots"]]) if "lots" in cols and len(r) > cols["lots"] else None
        if lots is None and "shares" in cols and len(r) > cols["shares"]:
            sh = parse_number(r[cols["shares"]])
            lots = (sh / LOT) if sh is not None else None
        if lots is None or lots == 0:
            continue
        avg = parse_number(r[cols["avg"]]) if "avg" in cols and len(r) > cols["avg"] else None
        out.append({"code": code, "lots": lots, "avg": avg})
    return out


def _s(d: Any) -> str:
    """Decimal to a plain string without trailing zeros or exponents (12.00 -> '12', 1E+2 -> '100')."""
    return format(Decimal(str(d)).normalize(), "f")


def diff(book_positions: dict[str, dict[str, Any]], broker: list[dict[str, Any]], avg_tol_pct: Decimal = Decimal("1.0")) -> dict[str, Any]:
    """Pure. ``book_positions`` = {code: {lots, avg_price}} (from the book), ``broker`` = parse_csv rows."""
    br = {r["code"]: r for r in broker}
    only_book = sorted(c for c in book_positions if c not in br)
    only_broker = sorted(c for c in br if c not in book_positions)
    lots_mismatch, avg_mismatch, matched = [], [], []
    for c in sorted(set(book_positions) & set(br)):
        bl, kl = Decimal(str(book_positions[c]["lots"])), Decimal(str(br[c]["lots"]))
        if bl != kl:
            lots_mismatch.append({"code": c, "book_lots": _s(bl), "broker_lots": _s(kl), "diff_lots": _s(kl - bl)})
            continue
        ba, ka = book_positions[c].get("avg_price"), br[c].get("avg")
        if ba is not None and ka is not None and Decimal(str(ba)) > 0:
            gap = (Decimal(str(ka)) - Decimal(str(ba))) / Decimal(str(ba)) * 100
            if abs(gap) > avg_tol_pct:
                avg_mismatch.append({"code": c, "lots": _s(bl), "book_avg": _s(ba), "broker_avg": _s(ka), "gap_pct": str(gap.quantize(Decimal("0.01")))})
                continue
        matched.append(c)
    ok = not (only_book or only_broker or lots_mismatch)
    return {"ok": ok, "matched": matched, "only_book": only_book, "only_broker": only_broker, "lots_mismatch": lots_mismatch,
            "avg_mismatch": avg_mismatch, "n_book": len(book_positions), "n_broker": len(br)}


def reconcile(conn: psycopg.Connection, book: str, rows: list[dict[str, Any]], *, actor: str = "operator", source: str | None = None) -> dict[str, Any]:
    """Diff the book's open positions against broker rows and journal the result (action ``reconcile``). Read-only on the book."""
    pos = {r["code"]: r for r in _rows(conn, "SELECT code, lots, avg_price FROM idx.position WHERE book = %s AND lots > 0", (book,),
                                        ["code", "lots", "avg_price"])}
    rep = diff(pos, rows)
    rep.update({"book": book, "source": source})
    journal.record(conn, book, actor, "reconcile", rationale=("clean" if rep["ok"] else f"{len(rep['only_book'])} only in book, "
                   f"{len(rep['only_broker'])} only at broker, {len(rep['lots_mismatch'])} lot mismatches"),
                   refs={k: rep[k] for k in ("ok", "matched", "only_book", "only_broker", "lots_mismatch", "avg_mismatch", "source")})
    return rep


def render(rep: dict[str, Any]) -> str:
    o = [f"reconcile {rep['book']}: {'CLEAN' if rep['ok'] else 'DIFFERENCES'} - {len(rep['matched'])} matched of {rep['n_book']} in book / {rep['n_broker']} at broker"]
    for c in rep["only_book"]:
        o.append(f"  only in book:   {c}")
    for c in rep["only_broker"]:
        o.append(f"  only at broker: {c}")
    for m in rep["lots_mismatch"]:
        o.append(f"  lots {m['code']}: book {m['book_lots']} vs broker {m['broker_lots']} (diff {m['diff_lots']})")
    for m in rep["avg_mismatch"]:
        o.append(f"  avg  {m['code']}: book {m['book_avg']} vs broker {m['broker_avg']} ({m['gap_pct']} %)")
    return "\n".join(o)


# ---------------------------------------------------------------------------------------------------------------- trades
# Evidence plan item 6 (operator 2026-09-26): the POSITION reconcile above says the book holds what the broker holds; an auditable
# track record also needs every TRADE to match the broker's statement - price, lots and fee - so the live return is the broker's,
# not the desk's own entry. Transaction-history export (Stockbit "Riwayat transaksi" and the like), header names recognised:
TRADE_HEADERS = {
    "date": ("date", "tanggal", "tgl", "tradedate", "transactiondate", "tanggaltransaksi", "waktu", "datetime", "time"),
    "code": HEADERS["code"],
    "side": ("side", "type", "action", "buysell", "bs", "jenis", "transaksi", "tipe", "order", "ordertype"),
    "lots": HEADERS["lots"],
    "shares": ("shares", "qty", "quantity", "lembar", "volume", "jumlahsaham", "filledqty", "donevolume"),
    "price": ("price", "harga", "doneprice", "hargadone", "tradeprice", "hargatransaksi", "filledprice", "avgprice"),
    "fee": ("fee", "fees", "commission", "komisi", "biaya", "brokerfee", "totalfee"),
}
_SIDE = {"b": "buy", "buy": "buy", "beli": "buy", "s": "sell", "sell": "sell", "jual": "sell"}
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y")


def _parse_date(s: str) -> str | None:
    from datetime import datetime
    t = (s or "").strip().replace("T", " ")
    head = t.split(" ")[0] if t[:4].isdigit() or "/" in t[:10] or "-" in t[:10] else t
    for fmt in _DATE_FORMATS:
        for cand in (head, t[:11], t):
            try:
                return datetime.strptime(cand.strip(), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def parse_trades_csv(text: str) -> list[dict[str, Any]]:
    """Transaction export -> rows {date, code, side, lots, price, fee}; rows missing date/code/side/quantity/price are dropped."""
    text = text.lstrip(chr(0xFEFF))
    try:
        delim = csv.Sniffer().sniff(text[:2048], delimiters=";,\t").delimiter
    except csv.Error:
        delim = ";" if text[:2048].count(";") > text[:2048].count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    cols, hi = None, None
    for i, r in enumerate(rows[:10]):
        norm = [_norm(h) for h in r]
        c: dict[str, int] = {}
        for role, names in TRADE_HEADERS.items():
            for j, h in enumerate(norm):
                if h in names:
                    c[role] = j
                    break
        if all(k in c for k in ("date", "code", "side", "price")) and ("lots" in c or "shares" in c):
            cols, hi = c, i
            break
    if cols is None or hi is None:
        raise ValueError(f"no transaction header (date, code, side, lots/shares, price) in the first rows: {rows[:1]}")
    out = []
    for r in rows[hi + 1:]:
        def g(k: str, r: list[str] = r) -> str | None:
            return r[cols[k]] if k in cols and len(r) > cols[k] else None
        code = re.sub(r"[^A-Z0-9]", "", (g("code") or "").upper().split(".")[0])
        side = _SIDE.get(re.sub(r"[^a-z]", "", (g("side") or "").lower()))
        d = _parse_date(g("date") or "")
        lots = parse_number(g("lots")) if "lots" in cols else None
        if lots is None and "shares" in cols:
            sh = parse_number(g("shares"))
            lots = sh / LOT if sh is not None else None
        price = parse_number(g("price"))
        if not (code and side and d and lots and price):
            continue
        out.append({"date": d, "code": code, "side": side, "lots": lots, "price": price,
                    "fee": parse_number(g("fee")) if "fee" in cols else None})
    return out


def diff_trades(book_fills: list[dict[str, Any]], broker: list[dict[str, Any]], price_tol: Decimal = Decimal("0.5")) -> dict[str, Any]:
    """Pure. Match broker trades to book fills by (date, code, side), aggregating partial fills (lots summed, price lot-weighted).
    -> matched count, the matches that differ in lots / price / fee, and what only one side has."""
    def agg(rows: list[dict[str, Any]]) -> dict[tuple, dict[str, Any]]:
        out: dict[tuple, dict[str, Any]] = {}
        for x in rows:
            k = (str(x["date"]), str(x["code"]).upper(), x["side"])
            a = out.setdefault(k, {"lots": Decimal(0), "value": Decimal(0), "fee": Decimal(0), "fee_known": True})
            lots = Decimal(str(x["lots"]))
            a["lots"] += lots
            a["value"] += lots * Decimal(str(x["price"]))
            if x.get("fee") is None:
                a["fee_known"] = False
            else:
                a["fee"] += Decimal(str(x["fee"]))
        return out
    b, s = agg(book_fills), agg(broker)
    matched = []
    for k in sorted(set(b) & set(s)):
        x, y = b[k], s[k]
        pb, ps = x["value"] / x["lots"], y["value"] / y["lots"]
        m: dict[str, Any] = {"date": k[0], "code": k[1], "side": k[2], "lots_book": _s(x["lots"]), "lots_broker": _s(y["lots"]),
                             "price_book": _s(round(pb, 2)), "price_broker": _s(round(ps, 2)), "lots_ok": x["lots"] == y["lots"],
                             "price_ok": abs(pb - ps) <= price_tol}
        if y["fee_known"]:
            m.update({"fee_book": _s(x["fee"]), "fee_broker": _s(y["fee"]), "fee_ok": abs(x["fee"] - y["fee"]) <= Decimal(1)})
        matched.append(m)
    bad = [m for m in matched if not (m["lots_ok"] and m["price_ok"] and m.get("fee_ok", True))]
    only_book, only_broker = sorted(set(b) - set(s)), sorted(set(s) - set(b))
    return {"matched": len(matched), "differences": bad, "only_book": [list(k) for k in only_book], "only_broker": [list(k) for k in only_broker],
            "ok": not bad and not only_book and not only_broker}


def reconcile_trades(conn: psycopg.Connection, book: str, rows: list[dict[str, Any]], *, actor: str = "operator",
                     source: str | None = None) -> dict[str, Any]:
    """Diff the broker's trades (the statement's date range) against idx.fill and journal the outcome; never changes the book."""
    if not rows:
        raise ValueError("no trades parsed from the statement")
    lo, hi = min(r["date"] for r in rows), max(r["date"] for r in rows)
    fills = _rows(conn, "SELECT trade_date AS date, code, side, lots, price, fee FROM idx.fill WHERE book = %s AND side IN ('buy', 'sell') "
                        "AND trade_date BETWEEN %s AND %s", (book, lo, hi), ["date", "code", "side", "lots", "price", "fee"])
    rep = {"book": book, "from": lo, "to": hi, "source": source, **diff_trades(fills, rows)}
    journal.record(conn, book, actor, "note", rationale=f"trade reconcile {lo}..{hi}: {rep['matched']} matched, {len(rep['differences'])} differ, "
                                                         f"{len(rep['only_book'])} only in book, {len(rep['only_broker'])} only at broker",
                   refs={k: rep[k] for k in ("source", "differences", "only_book", "only_broker")})
    return rep


def render_trades(rep: dict[str, Any]) -> str:
    o = [f"# trade reconcile {rep['book']} {rep['from']}..{rep['to']} ({rep.get('source') or 'statement'}): "
         + ("ALL MATCH" if rep["ok"] else "DIFFERENCES"), f"matched {rep['matched']}"]
    for m in rep["differences"]:
        o.append(f"  DIFF {m['date']} {m['code']} {m['side']}: lots {m['lots_book']} vs {m['lots_broker']}, "
                 f"price {m['price_book']} vs {m['price_broker']}" + (f", fee {m['fee_book']} vs {m['fee_broker']}" if "fee_book" in m else ""))
    o += [f"  only in book:   {' '.join(k)}" for k in rep["only_book"]]
    o += [f"  only at broker: {' '.join(k)}" for k in rep["only_broker"]]
    return "\n".join(o)
