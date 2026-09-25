"""Broker summary per name per date window (the operator's Stockbit data subscription; research feed, not a desk dependency).

API: ``GET https://exodus.stockbit.com/marketdetectors/{CODE}?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=N&investor_type=..&
market_board=..&transaction_type=..`` - one request = one name over one date window, per broker: buy/sell value, lots,
average. Authenticated like every other API in this package (Telegram, Yahoo): the API key comes from the environment,
``STOCKBIT_TOKEN`` in ``idx-local.env`` (gitignored); ``STOCKBIT_BS_URL`` optionally carries one example URL whose
enum parameters are reused verbatim (the defaults below otherwise).

Manners: one request per second by default, resumable (a window already stored with HTTP 200 is skipped), and the loop
stops on the first 401/403/429 (expired key, gated account, or the site pushing back) instead of retrying.

Raw payloads are stored whole (``idx.broker_summary_raw``) and parsed tolerantly into ``idx.broker_summary``; when the
real shape differs from the guesses in ``parse``, fix the parser and ``reparse`` from the raw table - nothing is refetched.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
import psycopg.types.json

from .card import _rows

logger = logging.getLogger(__name__)
TOKEN_ENV, URL_ENV = "STOCKBIT_TOKEN", "STOCKBIT_BS_URL"
REFRESH_ENV, ENV_FILE_ENV = "STOCKBIT_REFRESH_TOKEN", "STOCKBIT_ENV_FILE"
BASE = "https://exodus.stockbit.com/marketdetectors/"                       # legacy per-window feed; Pro-only since 2026-09-18
DIST_BASE = "https://exodus.stockbit.com/order-trade/broker/distribution"   # the free daily buyer->seller feed the desk uses now
REFRESH_URL = "https://exodus.stockbit.com/login/refresh"                   # POST {} with Authorization: Bearer <refresh token>
DEFAULT_PARAMS = {"investor_type": "INVESTOR_TYPE_ALL", "market_board": "MARKET_BOARD_REGULER", "transaction_type": "TRANSACTION_TYPE_NET"}
LIMIT = "100"
LOT = 100
# Verified against the live API 2026-09-24 (12 probes); everything else answers HTTP 400.
PERIOD_DAY, PERIOD_MONTH, PERIOD_3M, PERIOD_YEAR = "TB_PERIOD_LAST_1_DAY", "TB_PERIOD_LAST_1_MONTH", "TB_PERIOD_LAST_3_MONTHS", "TB_PERIOD_LAST_1_YEAR"
DIST_PERIODS = (PERIOD_DAY, PERIOD_MONTH, PERIOD_3M, PERIOD_YEAR)
DIST_INVESTORS = ("INVESTOR_TYPE_ALL", "INVESTOR_TYPE_FOREIGN", "INVESTOR_TYPE_DOMESTIC")
DIST_BOARDS = ("MARKET_TYPE_REGULER", "MARKET_TYPE_ALL", "MARKET_TYPE_TUNAI")
DATA_VALUE, DATA_VOLUME = "BROKER_DISTRIBUTION_DATA_TYPE_VALUE", "BROKER_DISTRIBUTION_DATA_TYPE_VOLUME"
DIST_DATA_TYPES = (DATA_VALUE, DATA_VOLUME)
# Stored board label: keep the three years of history's spelling, one label per distinct board.
BOARD_LABEL = {"MARKET_TYPE_REGULER": "MARKET_BOARD_REGULER", "MARKET_TYPE_ALL": "MARKET_BOARD_ALL", "MARKET_TYPE_TUNAI": "MARKET_BOARD_TUNAI"}
# What a daily capture asks for. CORE = the four windows of the whole market; DETAIL adds the investor split, the
# all-boards view (negotiated crossings included) and the lot view - 48 requests per name instead of 4.
MATRIX_CORE = [(per, "INVESTOR_TYPE_ALL", "MARKET_TYPE_REGULER", DATA_VALUE) for per in DIST_PERIODS]
EMPTY_STREAK = 3                 # empty answers in a row before the loop reads it as pushback rather than empty names
MATRIX_DETAIL = [(per, inv, brd, dt) for per in DIST_PERIODS for inv in DIST_INVESTORS for brd in ("MARKET_TYPE_REGULER", "MARKET_TYPE_ALL") for dt in DIST_DATA_TYPES]
Fetcher = Callable[[str, dict[str, str]], tuple[int, bytes]]


class BrokerFetchError(RuntimeError):
    pass


class BrokerAuthError(BrokerFetchError):
    """401/403: the key expired or the account is not allowed - stop, do not retry."""


class BrokerRateLimited(BrokerFetchError):
    """429: the site is pushing back - stop the run."""


class BrokerPaywall(BrokerAuthError):
    """402: the endpoint is behind a subscription for this account - stop, do not retry.

    The legacy ``marketdetectors`` endpoint moved behind Stockbit Pro on 2026-09-18; the daily feed
    reads the free ``order-trade/broker/distribution`` endpoint instead (``fetch_day``).
    """


# ---------------------------------------------------------------------------------------------------------------- config
def _db_access_token(conn: psycopg.Connection | None = None) -> str | None:
    """The stored Stockbit session from idx.feed_token - where the tokens live since 2026-09-25 (operator: "token nya
    ditaruh di db aja"). Opens its own connection when none is given; any failure reads as 'no token'."""
    from .feed import store as feed_store
    try:
        if conn is not None:
            tok = feed_store.load_token(conn)
        else:
            from ..shared.db import get_connection
            with get_connection() as c:
                tok = feed_store.load_token(c)
    except (psycopg.Error, OSError, ValueError) as e:
        logger.warning("idx broker: could not read the token from idx.feed_token - %s", e)
        return None
    return ((tok or {}).get("access_token") or "").strip() or None


def config(env: dict[str, str] | None = None, conn: psycopg.Connection | None = None) -> dict[str, Any]:
    """The access token comes from idx.feed_token. ``env`` given explicitly (tests, one-off calls) is read INSTEAD of the
    database; with no ``env`` the process environment is only a fallback for a machine with no stored session."""
    from_db = env is None
    env = os.environ if env is None else env
    key = (_db_access_token(conn) if from_db else None) or (env.get(TOKEN_ENV) or "").strip()
    if not key:
        raise BrokerAuthError(f"no Stockbit token: none in idx.feed_token and {TOKEN_ENV} is not set - paste the cookie at /idx/feed/relay")
    base, params = BASE, dict(DEFAULT_PARAMS)
    url = (env.get(URL_ENV) or "").strip()
    if url:
        u = urllib.parse.urlsplit(url)
        m = re.match(r"^(.*/marketdetectors/)[A-Z0-9]+/?$", u.path)
        if m:
            base = f"{u.scheme}://{u.netloc}{m.group(1)}"
        for k, v in urllib.parse.parse_qsl(u.query):
            if k in DEFAULT_PARAMS and v:
                params[k] = v
    return {"key": key, "base": base, "params": params}


def build_url(code: str, d_from: date, d_to: date, cfg: dict[str, Any]) -> str:
    q = {"from": d_from.isoformat(), "to": d_to.isoformat(), "limit": LIMIT, **cfg["params"]}
    return cfg["base"] + code.upper() + "?" + urllib.parse.urlencode(q)


def _urllib_fetch(url: str, headers: dict[str, str], timeout: float = 30.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def fetch(code: str, d_from: date, d_to: date, cfg: dict[str, Any] | None = None, fetcher: Fetcher | None = None) -> tuple[int, Any, str | None]:
    """-> (http_status, payload | None, error | None). Raises BrokerAuthError / BrokerRateLimited so loops stop."""
    cfg = cfg or config()
    headers = {"Authorization": f"Bearer {cfg['key']}", "X-Platform": "web", "Accept": "application/json",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) blackheart-idx research feed"}
    url = build_url(code, d_from, d_to, cfg)
    try:
        status, body = (fetcher or _urllib_fetch)(url, headers)
    except (urllib.error.URLError, OSError) as e:
        return 0, None, f"{type(e).__name__}: {e}"
    if status in (401, 403):
        raise BrokerAuthError(f"HTTP {status} for {code}: key expired or the account is not allowed")
    if status == 402:
        raise BrokerPaywall(f"HTTP 402 for {code}: this endpoint is Pro-only for this account")
    if status == 429:
        raise BrokerRateLimited(f"HTTP 429 for {code}: rate limited - stop and retry later")
    try:
        payload = json.loads(body.decode("utf-8")) if body else None
    except (ValueError, UnicodeDecodeError) as e:
        return status, None, f"not JSON: {e}"
    return status, payload, None if status == 200 else f"HTTP {status}"


# ---------------------------------------------------------------------------------------------------------------- parse
_NUM = re.compile(r"^-?[\d.,]+$")


def _num(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float | Decimal):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "")
    if re.match(r"^-?\d+(\.\d+)?[eE][+-]?\d+$", s):                # scientific notation as the API sends it
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    if not s or not _NUM.match(s):
        return None
    if "." in s and "," in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", "") if re.match(r"^-?\d{1,3}(,\d{3})+$", s) else s.replace(",", ".")
    elif "." in s and re.match(r"^-?\d{1,3}(\.\d{3})+$", s):      # Indonesian thousands ("12.345")
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _norm(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", k.lower())


def _pick(d: dict[str, Any], *names: str) -> Any:
    """First value among keys whose normalised name equals one of ``names``."""
    nd = {_norm(k): v for k, v in d.items()}
    for n in names:
        if n in nd:
            return nd[n]
    return None


def _side(item: dict[str, Any], side: str) -> dict[str, Decimal | None]:
    """buy/sell figures from a flat item ({"bval": ..} / {"buy_value": ..}) or a nested one ({"buy": {"value": ..}})."""
    s = side[0]                                                       # b | s
    nested = _pick(item, side, f"{side}er", f"{side}side")
    if isinstance(nested, dict):
        val = _num(_pick(nested, "value", "val", "amount", "totalvalue"))
        lot = _num(_pick(nested, "lot", "lots", "totallot"))
        vol = _num(_pick(nested, "volume", "vol", "shares", "qty"))
        avg = _num(_pick(nested, "avg", "average", "avgprice", "price"))
    else:
        val = _num(_pick(item, f"{s}val", f"{side}value", f"{side}val", f"{s}value", f"{side}amount", f"value{side}", f"{s}v"))
        lot = _num(_pick(item, f"{s}lot", f"{side}lot", f"{side}lots", f"lot{side}"))
        vol = _num(_pick(item, f"{s}vol", f"{side}volume", f"{side}vol", f"{side}shares", f"volume{side}"))
        avg = _num(_pick(item, f"{s}avg", f"{side}avg", f"{side}average", f"{side}avgprice", f"{side}price", f"avg{side}"))
    if lot is None and vol is not None:
        lot = vol / LOT
    return {"value": val, "lot": lot, "avg": avg}


def _broker_code(item: dict[str, Any]) -> str | None:
    v = _pick(item, "brokercode", "broker", "code", "brokerid", "id", "netbrokercode", "symbol")
    if isinstance(v, dict):
        v = _pick(v, "code", "brokercode", "id")
    if v is None:
        return None
    v = str(v).strip().upper()
    return v if 1 <= len(v) <= 4 and v.isalnum() else None


def _lists(payload: Any, path: str = "") -> list[tuple[str, list[dict[str, Any]]]]:
    out = []
    if isinstance(payload, list):
        if payload and all(isinstance(x, dict) for x in payload):
            out.append((path, payload))
        for i, x in enumerate(payload[:3]):
            out.extend(_lists(x, f"{path}[{i}]"))
    elif isinstance(payload, dict):
        for k, v in payload.items():
            out.extend(_lists(v, f"{path}.{k}" if path else k))
    return out


def _exact(payload: Any) -> list[dict[str, Any]] | None:
    """The shape seen 2026-09-17: data.broker_summary.brokers_buy / brokers_sell, one row per net buyer / net seller:
    netbs_broker_code, type (Asing|Lokal|Pemerintah), freq; buyers carry bvalv/blotv (gross buy value / shares) and bval/blot
    (net value / lots, positive); sellers svalv/slotv (gross sell) and sval/slot (net, negative)."""
    bs = payload.get("data", {}).get("broker_summary") if isinstance(payload, dict) else None
    if not isinstance(bs, dict) or not ("brokers_buy" in bs or "brokers_sell" in bs):
        return None
    rows = []
    for side, items in (("buy", bs.get("brokers_buy") or []), ("sell", bs.get("brokers_sell") or [])):
        for it in items:
            code = str(it.get("netbs_broker_code") or "").strip().upper()
            if not code:
                continue
            c = side[0]
            gross_v, gross_sh = _num(it.get(f"{c}valv")), _num(it.get(f"{c}lotv"))
            net_v, net_l = _num(it.get(f"{c}val")), _num(it.get(f"{c}lot"))
            avg = _num(it.get(f"netbs_{side}_avg_price"))
            buy = side == "buy"
            rows.append({"broker": code, "broker_name": None, "investor": it.get("type"), "freq": int(_num(it.get("freq")) or 0) or None,
                         "buy_value": gross_v if buy else None, "buy_lot": (gross_sh / LOT) if buy and gross_sh is not None else None,
                         "buy_avg": avg if buy else None,
                         "sell_value": None if buy else gross_v, "sell_lot": None if buy or gross_sh is None else gross_sh / LOT,
                         "sell_avg": None if buy else avg,
                         "net_value": net_v if net_v is not None else Decimal(0), "net_lot": net_l if net_l is not None else Decimal(0)})
    rows.sort(key=lambda r: r["net_value"], reverse=True)
    return rows


def parse_detector(payload: Any) -> dict[str, Any] | None:
    """data.bandar_detector -> one row: concentration of the top-1/3/5/10 net buyers (% of traded value), labels, counts."""
    bd = payload.get("data", {}).get("bandar_detector") if isinstance(payload, dict) else None
    if not isinstance(bd, dict):
        return None

    def pct(k):
        v = bd.get(k) or {}
        return _num(v.get("percent")) if isinstance(v, dict) else None

    def label(k):
        v = bd.get(k) or {}
        return v.get("accdist") if isinstance(v, dict) else None
    return {"value": _num(bd.get("value")), "volume": _num(bd.get("volume")), "average": _num(bd.get("average")),
            "total_buyer": int(_num(bd.get("total_buyer")) or 0), "total_seller": int(_num(bd.get("total_seller")) or 0),
            "number_broker_buysell": int(_num(bd.get("number_broker_buysell")) or 0), "broker_accdist": bd.get("broker_accdist"),
            "top1_pct": pct("top1"), "top3_pct": pct("top3"), "top5_pct": pct("top5"), "top10_pct": pct("top10"), "avg_pct": pct("avg"), "avg5_pct": pct("avg5"),
            "top1_label": label("top1"), "top3_label": label("top3"), "top5_label": label("top5"), "top10_label": label("top10")}


def parse(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The exact shape first; otherwise tolerant: find every list of broker rows (a combined list, or separate buy/sell lists
    merged by broker) and read buy/sell value/lot/avg by field-name patterns. Returns (rows, diagnostics)."""
    exact = _exact(payload)
    if exact is not None:
        return exact, {"lists_used": [("data.broker_summary", len(exact))], "keys_seen": ["exact"], "n": len(exact)}
    merged: dict[str, dict[str, Any]] = {}
    used, seen_keys = [], set()
    for path, items in _lists(payload):
        hit = 0
        for it in items:
            code = _broker_code(it)
            if not code:
                continue
            seen_keys.update(_norm(k) for k in it)
            b, s = _side(it, "buy"), _side(it, "sell")
            if all(v is None for v in (*b.values(), *s.values())):
                continue
            hit += 1
            row = merged.setdefault(code, {"broker": code, "broker_name": None, "investor": None, "freq": None, "buy_value": None, "buy_lot": None,
                                           "buy_avg": None, "sell_value": None, "sell_lot": None, "sell_avg": None})
            name = _pick(it, "brokername", "name", "fullname")
            if isinstance(name, str) and not row["broker_name"]:
                row["broker_name"] = name.strip()[:120]
            for k, v in (("buy_value", b["value"]), ("buy_lot", b["lot"]), ("buy_avg", b["avg"]),
                         ("sell_value", s["value"]), ("sell_lot", s["lot"]), ("sell_avg", s["avg"])):
                if v is not None:
                    row[k] = v
        if hit:
            used.append((path, hit))
    rows = []
    for r in merged.values():
        bv, sv = r["buy_value"] or Decimal(0), r["sell_value"] or Decimal(0)
        bl, sl = r["buy_lot"] or Decimal(0), r["sell_lot"] or Decimal(0)
        r["net_value"], r["net_lot"] = bv - sv, bl - sl
        rows.append(r)
    rows.sort(key=lambda r: r["net_value"], reverse=True)
    return rows, {"lists_used": used, "keys_seen": sorted(seen_keys)[:60], "n": len(rows)}


# ---------------------------------------------------------------------------------------------------------------- store
def store(conn: psycopg.Connection, code: str, d_from: date, d_to: date, cfg: dict[str, Any], status: int, payload: Any, error: str | None) -> tuple[int, int]:
    """Upsert the raw payload and its parsed rows; -> (raw_id, n_rows)."""
    p = cfg["params"]
    key = (code.upper(), d_from, d_to, p["investor_type"], p["market_board"], p["transaction_type"])
    dt = p.get("data_type") or DATA_VALUE
    per = p.get("period") or "LEGACY"                     # the per-window feed and the old 1-day snapshot carry no period
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.broker_summary_raw (code, date_from, date_to, investor_type, market_board, transaction_type, data_type, period, http_status, payload, error)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (code, date_from, date_to, investor_type, market_board, transaction_type, data_type, period) DO UPDATE SET
                           http_status = EXCLUDED.http_status, payload = EXCLUDED.payload, error = EXCLUDED.error, fetched_at = now()
                       RETURNING id""", (*key, dt, per, status, psycopg.types.json.Jsonb(payload) if payload is not None else None, error))
        row = cur.fetchone()
        raw_id = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
        n = _store_rows(cur, key, raw_id, payload)
    conn.commit()
    return raw_id, n


def _store_rows(cur, key, raw_id: int, payload: Any) -> int:
    cur.execute("DELETE FROM idx.broker_summary WHERE code = %s AND date_from = %s AND date_to = %s AND investor_type = %s AND market_board = %s AND transaction_type = %s", key)
    if payload is None:
        return 0
    rows, _ = parse_any(payload)
    cur.executemany("""INSERT INTO idx.broker_summary (code, date_from, date_to, investor_type, market_board, transaction_type, broker, broker_name,
                           buy_value, buy_lot, buy_avg, sell_value, sell_lot, sell_avg, net_value, net_lot, investor, freq, raw_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (code, date_from, date_to, investor_type, market_board, transaction_type, broker) DO UPDATE SET
                           net_value = idx.broker_summary.net_value + EXCLUDED.net_value, net_lot = idx.broker_summary.net_lot + EXCLUDED.net_lot,
                           sell_value = COALESCE(EXCLUDED.sell_value, idx.broker_summary.sell_value),
                           sell_lot = COALESCE(EXCLUDED.sell_lot, idx.broker_summary.sell_lot), sell_avg = COALESCE(EXCLUDED.sell_avg, idx.broker_summary.sell_avg)""",
                    [(*key, r["broker"], r["broker_name"], r["buy_value"], r["buy_lot"], r["buy_avg"], r["sell_value"], r["sell_lot"], r["sell_avg"],
                      r["net_value"], r["net_lot"], r.get("investor"), r.get("freq"), raw_id) for r in rows])
    cur.execute("DELETE FROM idx.broker_detector WHERE code = %s AND date_from = %s AND date_to = %s AND investor_type = %s AND market_board = %s AND transaction_type = %s", key)
    det = detector_any(payload)
    if det:
        cols = list(det)
        cur.execute(f"""INSERT INTO idx.broker_detector (code, date_from, date_to, investor_type, market_board, transaction_type, {', '.join(cols)}, raw_id)
                        VALUES ({', '.join(['%s'] * (7 + len(cols)))})""", (*key, *[det[c] for c in cols], raw_id))
    return len(rows)


def reparse(conn: psycopg.Connection, code: str | None = None) -> int:
    """Re-run ``parse`` over stored payloads (after a parser fix); -> rows written."""
    raws = _rows(conn, """SELECT id, code, date_from, date_to, investor_type, market_board, transaction_type, payload FROM idx.broker_summary_raw
                          WHERE http_status = 200 AND payload IS NOT NULL AND (%s::text IS NULL OR code = %s) ORDER BY id""", (code, code),
                 ["id", "code", "date_from", "date_to", "investor_type", "market_board", "transaction_type", "payload"])
    n = 0
    with conn.cursor() as cur:
        for r in raws:
            key = (r["code"], r["date_from"], r["date_to"], r["investor_type"], r["market_board"], r["transaction_type"])
            n += _store_rows(cur, key, r["id"], r["payload"])
    conn.commit()
    return n


# ------------------------------------------------------------------------------------------------------------- backfill
def windows(trading_days: list[date], start: date, end: date, days: int = 20) -> list[tuple[date, date]]:
    """Consecutive windows of ``days`` trading days, the last one ending at ``end`` (or the last trading day before it)."""
    td = [d for d in trading_days if start <= d <= end]
    out = []
    i = len(td)
    while i > 0:
        j = max(0, i - days)
        out.append((td[j], td[i - 1]))
        i = j
    return out[::-1]


def trading_days(conn: psycopg.Connection, start: date, end: date) -> list[date]:
    return [r["d"] for r in _rows(conn, "SELECT DISTINCT trade_date AS d FROM idx.bar WHERE source = 'idx' AND trade_date BETWEEN %s AND %s ORDER BY 1",
                                  (start, end), ["d"])]


def universe_codes(conn: psycopg.Connection, min_v60: float = 20e9, min_price: float = 1000) -> list[str]:
    """Names to feed: liquid (60-day median value) and priced above the tick-heavy band, on the latest bar."""
    return [r["code"] for r in _rows(conn, """
        SELECT b.code FROM idx.bar b JOIN idx.feature_daily f USING (code, trade_date) JOIN idx.listing l USING (code)
         WHERE b.trade_date = (SELECT max(trade_date) FROM idx.bar WHERE source = 'idx') AND b.source = 'idx'
           AND f.value_60d_median >= %s AND b.close >= %s AND l.board IN ('Utama', 'Pengembangan') ORDER BY f.value_60d_median DESC""",
        (min_v60, min_price), ["code"])]


def all_codes(conn: psycopg.Connection) -> list[str]:
    """Every name with a bar on the last trading day on the main or development board - the whole market, for capture."""
    return [r["code"] for r in _rows(conn, """
        SELECT b.code FROM idx.bar b JOIN idx.listing l USING (code)
         WHERE b.source = 'idx' AND b.trade_date = (SELECT max(trade_date) FROM idx.bar WHERE source = 'idx')
           AND l.board IN ('Utama', 'Pengembangan') ORDER BY b.code""", (), ["code"])]


def detail_codes(conn: psycopg.Connection, min_v60: float = 5e9) -> list[str]:
    """Names liquid enough for the 48-view detail matrix: 60-day median traded value >= min_v60 on the last bar."""
    return [r["code"] for r in _rows(conn, """
        SELECT f.code FROM idx.feature_daily f JOIN idx.listing l USING (code)
         WHERE f.trade_date = (SELECT max(trade_date) FROM idx.feature_daily) AND f.value_60d_median >= %s
           AND l.board IN ('Utama', 'Pengembangan') ORDER BY f.code""", (min_v60,), ["code"])]


def backfill(conn: psycopg.Connection, codes: list[str], start: date, end: date, *, window: int = 20, rps: float = 1.0,
             cfg: dict[str, Any] | None = None, fetcher: Fetcher | None = None, sleep: Callable[[float], None] = time.sleep,
             resume: bool = True, max_requests: int | None = None, log: Callable[[str], None] = logger.info) -> dict[str, Any]:
    """Fetch every (code, window) once, politely; stops on auth/rate-limit errors. -> counts."""
    cfg = cfg or config()
    p = cfg["params"]
    td = trading_days(conn, start, end)
    wins = windows(td, start, end, window)
    done = set()
    if resume:
        done = {(r["code"], r["date_from"], r["date_to"]) for r in _rows(conn, """
            SELECT code, date_from, date_to FROM idx.broker_summary_raw WHERE http_status = 200 AND investor_type = %s AND market_board = %s AND transaction_type = %s""",
            (p["investor_type"], p["market_board"], p["transaction_type"]), ["code", "date_from", "date_to"])}
    res = {"codes": len(codes), "windows": len(wins), "requested": 0, "skipped": 0, "ok": 0, "failed": 0, "rows": 0, "stopped": None}
    for code in codes:
        for d_from, d_to in wins:
            if (code.upper(), d_from, d_to) in done:
                res["skipped"] += 1
                continue
            if max_requests is not None and res["requested"] >= max_requests:
                res["stopped"] = f"max_requests {max_requests}"
                return res
            try:
                status, payload, err = fetch(code, d_from, d_to, cfg, fetcher)
            except BrokerFetchError as e:
                res["stopped"] = str(e)
                log(f"idx broker: stopped - {e}")
                return res
            res["requested"] += 1
            _, n = store(conn, code, d_from, d_to, cfg, status, payload, err)
            if status == 200 and err is None:
                res["ok"] += 1
                res["rows"] += n
            else:
                res["failed"] += 1
                log(f"idx broker: {code} {d_from}..{d_to} -> {status} {err}")
            sleep(1.0 / rps if rps > 0 else 0)
    return res


def show(conn: psycopg.Connection, code: str, n: int = 15) -> list[dict[str, Any]]:
    """The latest window's brokers for a name, by net value."""
    return _rows(conn, """
        WITH w AS (SELECT date_from, date_to FROM idx.broker_summary WHERE code = %s ORDER BY date_to DESC, date_from DESC LIMIT 1)
        SELECT s.date_from, s.date_to, s.broker, s.broker_name, s.investor, s.freq, s.buy_value, s.buy_lot, s.buy_avg, s.sell_value, s.sell_lot, s.sell_avg,
               s.net_value, s.net_lot
          FROM idx.broker_summary s JOIN w USING (date_from, date_to) WHERE s.code = %s ORDER BY s.net_value DESC LIMIT %s""",
        (code.upper(), code.upper(), n), ["date_from", "date_to", "broker", "broker_name", "investor", "freq", "buy_value", "buy_lot", "buy_avg", "sell_value",
                                         "sell_lot", "sell_avg", "net_value", "net_lot"])


def detector(conn: psycopg.Connection, code: str, n: int = 5) -> list[dict[str, Any]]:
    cols = ["date_from", "date_to", "value", "total_buyer", "total_seller", "broker_accdist", "top1_pct", "top3_pct", "top5_pct", "top10_pct", "top1_label", "top5_label"]
    return _rows(conn, f"SELECT {', '.join(cols)} FROM idx.broker_detector WHERE code = %s ORDER BY date_to DESC LIMIT %s", (code.upper(), n), cols)


# ============================================================================================= daily distribution feed
# Stockbit closed the per-window ``marketdetectors`` endpoint behind Pro (HTTP 402) on 2026-09-18. The free
# ``order-trade/broker/distribution`` endpoint still serves, per name, a buyer->seller value matrix, free.
#
# Windows (re-probed 2026-09-24, research/IDX_BREAKOUT_ACCUM_2026-09-24.md section D): ``period=`` DOES take longer
# windows - TB_PERIOD_LAST_1_DAY, LAST_1_MONTH, LAST_3_MONTHS and LAST_1_YEAR all answer 200 and the payload's
# start_date / end_date span the stated window (BBCA's top buy broker: Rp 40,695 bn over LAST_1_YEAR against Rp 138 bn
# over LAST_1_DAY, so the aggregation is real). Every other enum tried answers 400. What is NOT available is moving the
# window into the past: ``date=``, ``end_date=``, ``to=`` and ``start_date=`` are all ignored and the window always ends
# on the last trading day. So: aggregates yes, history no - the daily feed still accumulates one snapshot per day going
# forward and stores it as a one-day "window" (date_from == date_to) in the same ``idx.broker_summary`` /
# ``idx.broker_detector`` tables. The window history backfilled to 2023 stays untouched.

def _is_distribution(payload: Any) -> bool:
    return bool(isinstance(payload, dict) and isinstance(payload.get("data"), dict)
                and isinstance(payload["data"].get("by_value"), dict))


def parse_any(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Route to the right parser by payload shape: the daily distribution feed, else the legacy window feed."""
    if _is_distribution(payload):
        return parse_distribution(payload)
    return parse(payload)


def detector_any(payload: Any) -> dict[str, Any] | None:
    if _is_distribution(payload):
        return distribution_detector(payload)
    return parse_detector(payload)


def _dist_sides(payload: Any) -> tuple[dict[str, tuple[Decimal, str]], dict[str, tuple[Decimal, str]]]:
    """(buy, sell) maps broker -> (gross value, investor type) from data.by_value.top_broker_*[].detail."""
    bv = (payload.get("data", {}) or {}).get("by_value", {}) if isinstance(payload, dict) else {}

    def side(name: str) -> dict[str, tuple[Decimal, str]]:
        out: dict[str, tuple[Decimal, str]] = {}
        for it in bv.get(name) or []:
            d = it.get("detail") if isinstance(it, dict) else None
            if not isinstance(d, dict) or not d.get("code"):
                continue
            out[str(d["code"]).strip()] = (_num(d.get("amount")) or Decimal(0), (d.get("type") or None))
        return out

    return side("top_broker_buy"), side("top_broker_sell")


def parse_distribution(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """data.by_value.top_broker_buy/sell -> one row per broker: gross buy/sell value, net, investor type.

    The distribution feed carries value only (no lots, avg price, frequency or broker name), so those stay NULL.
    """
    buy, sell = _dist_sides(payload)
    rows = []
    for code in sorted(set(buy) | set(sell)):
        bvv, btype = buy.get(code, (Decimal(0), None))
        svv, stype = sell.get(code, (Decimal(0), None))
        rows.append({"broker": code, "broker_name": None, "investor": btype or stype, "freq": None,
                     "buy_value": bvv or None, "buy_lot": None, "buy_avg": None,
                     "sell_value": svv or None, "sell_lot": None, "sell_avg": None,
                     "net_value": (bvv - svv), "net_lot": None})
    rows.sort(key=lambda r: r["net_value"], reverse=True)
    return rows, {"lists_used": [("data.by_value", len(rows))], "keys_seen": ["distribution"], "n": len(rows)}


def distribution_detector(payload: Any) -> dict[str, Any] | None:
    """Concentration of the day's net buyers, reconstructed from the distribution matrix (mirrors the old detector)."""
    rows, _ = parse_distribution(payload)
    if not rows:
        return None
    nets = [r["net_value"] for r in rows]
    buyers = [n for n in nets if n > 0]
    sellers = [n for n in nets if n < 0]
    total_buy = sum(buyers) or Decimal(0)
    traded = sum((r["buy_value"] or Decimal(0)) for r in rows)                        # gross value bought = value traded
    top = sorted(buyers, reverse=True)

    def share(k: int) -> Decimal | None:
        return (sum(top[:k]) / total_buy * 100) if total_buy > 0 else None

    return {"value": traded or None, "volume": None, "average": None,
            "total_buyer": len(buyers), "total_seller": len(sellers),
            "number_broker_buysell": len(rows), "broker_accdist": None,
            "top1_pct": share(1), "top3_pct": share(3), "top5_pct": share(5), "top10_pct": share(10),
            "avg_pct": None, "avg5_pct": None,
            "top1_label": None, "top3_label": None, "top5_label": None, "top10_label": None}


def fetch_day(code: str, cfg: dict[str, Any] | None = None, fetcher: Fetcher | None = None) -> tuple[int, Any, date | None, str | None]:
    """Latest-day broker distribution for one name -> (http_status, payload | None, trade_date | None, error | None).

    Raises BrokerPaywall / BrokerAuthError / BrokerRateLimited so a snapshot loop stops cleanly.
    """
    cfg = cfg or config()
    headers = {"Authorization": f"Bearer {cfg['key']}", "X-Platform": "web", "Accept": "application/json",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) blackheart-idx research feed"}
    q = {"date": "", "symbol": code.upper(), "investor_type": "INVESTOR_TYPE_ALL", "market_board": "MARKET_TYPE_REGULER",
         "data_type": "BROKER_DISTRIBUTION_DATA_TYPE_VALUE", "period": "TB_PERIOD_LAST_1_DAY"}
    url = DIST_BASE + "?" + urllib.parse.urlencode(q)
    try:
        status, body = (fetcher or _urllib_fetch)(url, headers)
    except (urllib.error.URLError, OSError) as e:
        return 0, None, None, f"{type(e).__name__}: {e}"
    if status in (401, 403):
        raise BrokerAuthError(f"HTTP {status} for {code}: key expired or the account is not allowed")
    if status == 402:
        raise BrokerPaywall(f"HTTP 402 for {code}: broker distribution is Pro-only for this account")
    if status == 429:
        raise BrokerRateLimited(f"HTTP 429 for {code}: rate limited - stop and retry later")
    try:
        payload = json.loads(body.decode("utf-8")) if body else None
    except (ValueError, UnicodeDecodeError) as e:
        return status, None, None, f"not JSON: {e}"
    d = None
    if isinstance(payload, dict):
        di = (payload.get("data") or {}).get("date_info") if isinstance(payload.get("data"), dict) else None
        if di:
            try:
                d = date.fromisoformat(str(di)[:10])
            except ValueError:
                d = None
    return status, payload, d, None if status == 200 else f"HTTP {status}"


def snapshot(conn: psycopg.Connection, codes: list[str], cfg: dict[str, Any] | None = None, *, rps: float = 1.0,
             fetcher: Fetcher | None = None, sleep: Callable[[float], None] = time.sleep, resume: bool = True,
             expected_date: date | None = None, log: Callable[[str], None] = logger.info) -> dict[str, Any]:
    """Store each name's latest-day broker distribution as a one-day window (date_from == date_to). Resumable per
    (code, that day); stops cleanly on auth/paywall/rate-limit. -> counts."""
    cfg = cfg or config()
    p = cfg["params"]
    done: set[tuple[str, date]] = set()
    if resume and expected_date is not None:
        done = {(r["code"], expected_date) for r in _rows(conn, """
            SELECT code FROM idx.broker_summary_raw WHERE http_status = 200 AND date_from = date_to AND date_to = %s
              AND investor_type = %s AND market_board = %s AND transaction_type = %s""",
            (expected_date, p["investor_type"], p["market_board"], p["transaction_type"]), ["code"])}
    res = {"codes": len(codes), "requested": 0, "skipped": 0, "ok": 0, "failed": 0, "rows": 0, "date": None, "stopped": None}
    for code in codes:
        cu = code.upper()
        if expected_date is not None and (cu, expected_date) in done:
            res["skipped"] += 1
            continue
        try:
            status, payload, d, err = fetch_day(cu, cfg, fetcher)
        except BrokerFetchError as e:
            res["stopped"] = str(e)
            log(f"idx broker snapshot: stopped - {e}")
            return res
        res["requested"] += 1
        if status == 200 and d is not None:
            _, n = store(conn, cu, d, d, cfg, status, payload, err)
            res["ok"] += 1
            res["rows"] += n
            res["date"] = res["date"] or str(d)
        else:
            res["failed"] += 1
            log(f"idx broker snapshot: {cu} -> {status} {err or 'no date'}")
        sleep(1.0 / rps if rps > 0 else 0)
    return res


# ======================================================================================= wide capture (all windows)
# Probed 2026-09-24: the free distribution endpoint answers for four rolling windows, three investor splits, three
# boards and two data types, and every payload carries the buyer -> seller matrix. ``capture`` walks a matrix of those
# for a list of names, stores the per-broker totals (idx.broker_summary), the matrix (idx.broker_flow) and the payload
# itself (idx.broker_summary_raw), and is resumable: a (name, window, view) already stored with HTTP 200 is skipped.

def dist_params(period: str, investor_type: str, market_board: str, data_type: str) -> dict[str, str]:
    return {"period": period, "investor_type": investor_type, "market_board": market_board, "data_type": data_type}


def fetch_dist(code: str, period: str = PERIOD_DAY, investor_type: str = "INVESTOR_TYPE_ALL",
               market_board: str = "MARKET_TYPE_REGULER", data_type: str = DATA_VALUE,
               cfg: dict[str, Any] | None = None, fetcher: Fetcher | None = None) -> tuple[int, Any, date | None, date | None, str | None]:
    """One distribution view -> (status, payload | None, window start, window end, error). Raises the stop-the-loop errors."""
    cfg = cfg or config()
    headers = {"Authorization": f"Bearer {cfg['key']}", "X-Platform": "web", "Accept": "application/json",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) blackheart-idx research feed"}
    q = {"date": "", "symbol": code.upper(), "investor_type": investor_type, "market_board": market_board,
         "data_type": data_type, "period": period}
    try:
        status, body = (fetcher or _urllib_fetch)(DIST_BASE + "?" + urllib.parse.urlencode(q), headers)
    except (urllib.error.URLError, OSError) as e:
        return 0, None, None, None, f"{type(e).__name__}: {e}"
    if status in (401, 403):
        raise BrokerAuthError(f"HTTP {status} for {code}: key expired or the account is not allowed")
    if status == 402:
        raise BrokerPaywall(f"HTTP 402 for {code}: broker distribution is Pro-only for this account")
    if status == 429:
        raise BrokerRateLimited(f"HTTP 429 for {code}: rate limited - stop and retry later")
    try:
        payload = json.loads(body.decode("utf-8")) if body else None
    except (ValueError, UnicodeDecodeError) as e:
        return status, None, None, None, f"not JSON: {e}"
    d_from = d_to = None
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        def day(v):
            try:
                return date.fromisoformat(str(v)[:10])
            except (ValueError, TypeError):
                return None
        d_to = day(data.get("end_date")) or day(data.get("date_info"))
        d_from = day(data.get("start_date")) or d_to
    return status, payload, d_from, d_to, None if status == 200 else f"HTTP {status}"


def _dist_block(payload: Any, data_type: str) -> dict[str, Any]:
    """The by_value or by_volume block, whichever this data_type filled."""
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}
    blk = data.get("by_volume" if data_type == DATA_VOLUME else "by_value")
    return blk if isinstance(blk, dict) else {}


def parse_dist_totals(payload: Any, data_type: str = DATA_VALUE) -> list[dict[str, Any]]:
    """One row per broker: its gross buy and sell on this view, plus the net. Value or lots, per data_type."""
    blk = _dist_block(payload, data_type)
    sides: dict[str, dict[str, Any]] = {}
    for name, side in (("top_broker_buy", "buy"), ("top_broker_sell", "sell")):
        for it in blk.get(name) or []:
            det = it.get("detail") if isinstance(it, dict) else None
            if not isinstance(det, dict) or not det.get("code"):
                continue
            b = str(det["code"]).strip()
            r = sides.setdefault(b, {"broker": b, "investor": det.get("type") or None, "buy": None, "sell": None})
            r[side] = (r[side] or Decimal(0)) + (_num(det.get("amount")) or Decimal(0))
            r["investor"] = r["investor"] or det.get("type") or None
    # a side the broker is absent from stays NULL (it was below the top-12 cut, not zero); the net treats it as zero
    rows = [{"broker": r["broker"], "investor": r["investor"], "buy": r["buy"], "sell": r["sell"],
             "net": (r["buy"] or Decimal(0)) - (r["sell"] or Decimal(0))} for r in sides.values()]
    rows.sort(key=lambda r: r["net"], reverse=True)
    return rows


def parse_dist_edges(payload: Any, data_type: str = DATA_VALUE) -> list[dict[str, Any]]:
    """The buyer -> seller matrix: one row per (side, broker, counterparty)."""
    blk = _dist_block(payload, data_type)
    out = []
    for name, side in (("top_broker_buy", "BUY"), ("top_broker_sell", "SELL")):
        for it in blk.get(name) or []:
            det = it.get("detail") if isinstance(it, dict) else None
            if not isinstance(det, dict) or not det.get("code"):
                continue
            broker, btype = str(det["code"]).strip(), det.get("type") or None
            for e in it.get("distribute_to") or []:
                if not isinstance(e, dict) or not e.get("code"):
                    continue
                out.append({"side": side, "broker": broker, "broker_type": btype, "counterparty": str(e["code"]).strip(),
                            "counterparty_type": e.get("type") or None, "amount": _num(e.get("amount")) or Decimal(0)})
    return out


def store_dist(conn: psycopg.Connection, code: str, d_from: date, d_to: date, period: str, investor_type: str,
               market_board: str, data_type: str, status: int, payload: Any, error: str | None) -> tuple[int, int, int]:
    """Upsert one distribution view -> (raw_id, broker rows, matrix edges). Value and lots merge into the same rows."""
    board = BOARD_LABEL.get(market_board, market_board)
    key = (code.upper(), d_from, d_to, investor_type, board, "TRANSACTION_TYPE_NET")
    is_vol = data_type == DATA_VOLUME
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.broker_summary_raw (code, date_from, date_to, investor_type, market_board, transaction_type, data_type, period,
                           http_status, payload, error)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (code, date_from, date_to, investor_type, market_board, transaction_type, data_type, period) DO UPDATE SET
                           http_status = EXCLUDED.http_status, payload = EXCLUDED.payload, error = EXCLUDED.error, fetched_at = now()
                       RETURNING id""", (*key, data_type, period, status,
                                         psycopg.types.json.Jsonb(payload) if payload is not None else None, error))
        row = cur.fetchone()
        raw_id = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
        if payload is None or status != 200:
            conn.commit()
            return raw_id, 0, 0
        totals = parse_dist_totals(payload, data_type)
        if is_vol:
            cur.executemany("""INSERT INTO idx.broker_summary (code, date_from, date_to, investor_type, market_board, transaction_type, broker,
                                   buy_lot, sell_lot, net_lot, investor, period, raw_id)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (code, date_from, date_to, investor_type, market_board, transaction_type, broker) DO UPDATE SET
                                   buy_lot = EXCLUDED.buy_lot, sell_lot = EXCLUDED.sell_lot, net_lot = EXCLUDED.net_lot,
                                   investor = COALESCE(idx.broker_summary.investor, EXCLUDED.investor),
                                   period = COALESCE(idx.broker_summary.period, EXCLUDED.period), fetched_at = now()""",
                            [(*key, r["broker"], r["buy"], r["sell"], r["net"], r["investor"], period, raw_id) for r in totals])
        else:
            cur.executemany("""INSERT INTO idx.broker_summary (code, date_from, date_to, investor_type, market_board, transaction_type, broker,
                                   buy_value, sell_value, net_value, investor, period, raw_id)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (code, date_from, date_to, investor_type, market_board, transaction_type, broker) DO UPDATE SET
                                   buy_value = EXCLUDED.buy_value, sell_value = EXCLUDED.sell_value, net_value = EXCLUDED.net_value,
                                   investor = COALESCE(EXCLUDED.investor, idx.broker_summary.investor),
                                   period = EXCLUDED.period, raw_id = EXCLUDED.raw_id, fetched_at = now()""",
                            [(*key, r["broker"], r["buy"], r["sell"], r["net"], r["investor"], period, raw_id) for r in totals])
            det = distribution_detector(payload)
            if det:
                cols = list(det)
                cur.execute("DELETE FROM idx.broker_detector WHERE code = %s AND date_from = %s AND date_to = %s AND investor_type = %s"
                            " AND market_board = %s AND transaction_type = %s", key)
                cur.execute(f"""INSERT INTO idx.broker_detector (code, date_from, date_to, investor_type, market_board, transaction_type,
                                    {', '.join(cols)}, period, raw_id)
                                VALUES ({', '.join(['%s'] * (6 + len(cols) + 2))})""", (*key, *[det[c] for c in cols], period, raw_id))
        edges = parse_dist_edges(payload, data_type)
        amount_col = "volume" if is_vol else "value"
        cur.executemany(f"""INSERT INTO idx.broker_flow (code, date_from, date_to, investor_type, market_board, side, broker, counterparty,
                                broker_type, counterparty_type, {amount_col}, period, raw_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (code, date_from, date_to, investor_type, market_board, period, side, broker, counterparty) DO UPDATE SET
                                {amount_col} = EXCLUDED.{amount_col}, broker_type = COALESCE(EXCLUDED.broker_type, idx.broker_flow.broker_type),
                                counterparty_type = COALESCE(EXCLUDED.counterparty_type, idx.broker_flow.counterparty_type), fetched_at = now()""",
                        [(code.upper(), d_from, d_to, investor_type, board, e["side"], e["broker"], e["counterparty"],
                          e["broker_type"], e["counterparty_type"], e["amount"], period, raw_id) for e in edges])
    conn.commit()
    return raw_id, len(totals), len(edges)


def _captured(conn: psycopg.Connection, day: date) -> set[tuple[str, str, str, str, str]]:
    """(code, period, investor_type, stored board label, data_type) already stored OK for a window ending on `day`."""
    return {(r["code"], r["period"], r["investor_type"], r["market_board"], r["data_type"]) for r in _rows(conn, """
        SELECT code, period, investor_type, market_board, data_type FROM idx.broker_summary_raw
         WHERE http_status = 200 AND date_to = %s AND period <> 'LEGACY'""", (day,),
        ["code", "period", "investor_type", "market_board", "data_type"])}


def _rest_until_data(code, period, inv, board, dtype, cfg, fetcher, sleep, backoff, max_backoffs, res, log):
    """Rest and re-ask the same view. -> the fetch result once data comes back, or None when resting stops helping."""
    for _ in range(max_backoffs):
        res["backoffs"] += 1
        log(f"idx broker capture: empty payloads - resting {backoff:.0f} s before retrying {code} {period}")
        sleep(backoff)
        out = fetch_dist(code, period, inv, board, dtype, cfg, fetcher)
        res["requested"] += 1
        if out[0] == 200 and out[3] is not None:
            return out
    return None


def capture(conn: psycopg.Connection, codes: list[str], matrix: list[tuple[str, str, str, str]] | None = None,
            cfg: dict[str, Any] | None = None, *, rps: float = 1.0, fetcher: Fetcher | None = None,
            sleep: Callable[[float], None] = time.sleep, resume: bool = True, expected_date: date | None = None,
            max_requests: int | None = None, empty_backoff: float = 60.0, max_backoffs: int = 2,
            log: Callable[[str], None] = logger.info) -> dict[str, Any]:
    """Walk `matrix` (period, investor_type, market_board, data_type) over `codes`. Resumable, one request per second,
    stops on the first auth/paywall/rate-limit. -> counts.

    Throttling looks like success here. Measured 2026-09-24: after roughly a thousand requests the endpoint keeps
    answering HTTP 200 but with an empty payload (blank ``date_info``, no matrix), and it serves data again after about
    a minute of rest - there is no 429 to stop on. A single empty answer is also what a name with no broker prints in
    the window looks like, so one cannot be told from the other in isolation: this counts empties, and only when
    `EMPTY_STREAK` arrive in a row treats it as pushback - rest `empty_backoff` seconds, retry the same view, and give
    up the run after `max_backoffs` rests that change nothing. Empty answers are never stored, so a later run retries
    them instead of resuming over a hole."""
    cfg = cfg or config()
    matrix = list(matrix or MATRIX_CORE)
    done = _captured(conn, expected_date) if (resume and expected_date is not None) else set()
    res = {"codes": len(codes), "views": len(matrix), "requested": 0, "skipped": 0, "ok": 0, "failed": 0, "empty": 0,
           "rows": 0, "edges": 0, "backoffs": 0, "date": None, "stopped": None}
    streak = 0
    for code in codes:
        cu = code.upper()
        for period, inv, board, dtype in matrix:
            if (cu, period, inv, BOARD_LABEL.get(board, board), dtype) in done:
                res["skipped"] += 1
                continue
            if max_requests is not None and res["requested"] >= max_requests:
                res["stopped"] = f"max requests {max_requests}"
                return res
            try:
                status, payload, d_from, d_to, err = fetch_dist(cu, period, inv, board, dtype, cfg, fetcher)
            except BrokerFetchError as e:
                res["stopped"] = str(e)
                log(f"idx broker capture: stopped - {e}")
                return res
            res["requested"] += 1
            if status == 200 and d_to is not None:
                _, n, ne = store_dist(conn, cu, d_from or d_to, d_to, period, inv, board, dtype, status, payload, err)
                res["ok"] += 1
                res["rows"] += n
                res["edges"] += ne
                res["date"] = res["date"] or str(d_to)
                streak = 0
            elif status == 200:                                   # answered, but with nothing in it: empty name or throttle
                res["empty"] += 1
                streak += 1
                if streak >= EMPTY_STREAK:
                    rested = _rest_until_data(cu, period, inv, board, dtype, cfg, fetcher, sleep, empty_backoff,
                                              max_backoffs, res, log)
                    if rested is None:
                        res["stopped"] = f"empty payloads after {res['backoffs']} rests - rate limited, resume later"
                        log(f"idx broker capture: stopped - {res['stopped']}")
                        return res
                    status, payload, d_from, d_to, err = rested
                    streak = 0
                    if status == 200 and d_to is not None:
                        _, n, ne = store_dist(conn, cu, d_from or d_to, d_to, period, inv, board, dtype, status, payload, err)
                        res["ok"] += 1
                        res["rows"] += n
                        res["edges"] += ne
                        res["date"] = res["date"] or str(d_to)
            else:
                res["failed"] += 1
                log(f"idx broker capture: {cu} {period} {inv} {board} {dtype} -> {status} {err or 'no date'}")
            sleep(1.0 / rps if rps > 0 else 0)
    return res


# ==================================================================================================== token refresh (#2)
# The pasted STOCKBIT_TOKEN is a 24 h session JWT; the refresh token lasts 7 days. Verified 2026-09-22 against the live
# API: ``POST /login/refresh`` with ``Authorization: Bearer <refresh token>`` and an empty JSON body answers
# ``{"data": {"access": {"token", "expired_at"}, "refresh": {"token", "expired_at"}}}`` - the refresh token rotates every
# time. Before a run the feed refreshes from the newest refresh token it can see (idx-local.env or the relay row in
# ``idx.feed_token``), then writes the pair back to both places, so neither the nightly snapshot nor the tick feed
# needs a daily paste.

Poster = Callable[[str, dict[str, Any], str | None], tuple[int, bytes]]


def _json_post(url: str, body: dict[str, Any], bearer: str | None = None, timeout: float = 30.0) -> tuple[int, bytes]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json", "X-Platform": "web",
               "Origin": "https://stockbit.com", "Referer": "https://stockbit.com/",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) blackheart-idx research feed"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _find_token(obj: Any, wanted: tuple[str, ...]) -> str | None:
    """Depth-first search for the first non-empty string under a key whose normalised name matches ``wanted``."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v and _norm(k) in wanted:
                return v
        for v in obj.values():
            got = _find_token(v, wanted)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_token(v, wanted)
            if got:
                return got
    return None


def _find_subtree(obj: Any, wanted: tuple[str, ...]) -> Any:
    """Depth-first search for the first dict under a key whose normalised name matches ``wanted``."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and _norm(k) in wanted:
                return v
        for v in obj.values():
            got = _find_subtree(v, wanted)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_subtree(v, wanted)
            if got is not None:
                return got
    return None


def extract_tokens(resp: Any) -> tuple[str | None, str | None]:
    """(access_token, refresh_token | None) from the /login/refresh response - the nested shape
    ``{"access": {"token": ..}, "refresh": {"token": ..}}`` first, then a tolerant flat search."""
    access_sub = _find_subtree(resp, ("access", "accesstoken", "access_token"))
    refresh_sub = _find_subtree(resp, ("refresh", "refreshtoken", "refresh_token"))
    access = _find_token(access_sub, ("token",)) if access_sub else None
    refresh = _find_token(refresh_sub, ("token",)) if refresh_sub else None
    if not access:
        access = _find_token(resp, ("accesstoken", "access", "access_token", "token", "idtoken", "id_token", "jwt"))
    if not refresh:
        refresh = _find_token(resp, ("refreshtoken", "refresh", "refresh_token"))
    return access, refresh


def _jwt_claim(tok: str, key: str) -> int:
    """An integer claim (``iat``/``exp``) of a JWT, 0 when the token is not a JWT or lacks the claim."""
    try:
        import base64
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return int(json.loads(base64.urlsafe_b64decode(p)).get(key) or 0)
    except (IndexError, ValueError, TypeError):
        return 0


def refresh_access_token(refresh_token: str, poster: Poster | None = None) -> tuple[str, str | None, Any]:
    """Refresh token as Bearer, empty body -> (new access token, rotated refresh token | None, raw response). Raises on failure."""
    status, body = (poster or _json_post)(REFRESH_URL, {}, refresh_token)
    try:
        resp = json.loads(body.decode("utf-8")) if body else None
    except (ValueError, UnicodeDecodeError) as e:
        raise BrokerFetchError(f"refresh: response was not JSON ({e})") from e
    if status != 200:
        raise BrokerAuthError(f"refresh: HTTP {status} {json.dumps(resp)[:200] if resp is not None else ''}")
    access, rotated = extract_tokens(resp)
    if not access:
        raise BrokerFetchError(f"refresh: no access token in response (keys {list(resp)[:8] if isinstance(resp, dict) else type(resp).__name__})")
    return access, rotated, resp


def _default_env_file(env: dict[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    p = (env.get(ENV_FILE_ENV) or "").strip()
    if p:
        return p
    for cand in ("idx-local.env", os.path.join(os.getcwd(), "idx-local.env")):
        if os.path.isfile(cand):
            return cand
    return None


def write_env_token(path: str, key: str, value: str) -> None:
    """Set ``key=value`` in a dotenv file: replace the line (commented or not) if present, else append."""
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    pat = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=")
    new = f"{key}={value}"
    for i, ln in enumerate(lines):
        if pat.match(ln):
            lines[i] = new
            break
    else:
        lines.append(new)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _relay_refresh_token(conn: psycopg.Connection | None) -> str | None:
    """The refresh token the browser relay (or a previous refresh) left in ``idx.feed_token``."""
    if conn is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT refresh_token FROM idx.feed_token WHERE id = 1")
        r = cur.fetchone()
    v = (r["refresh_token"] if isinstance(r, dict) else r[0]) if r else None
    return str(v).strip() if v else None


def newest_refresh_token(env: dict[str, str] | None = None, conn: psycopg.Connection | None = None) -> str | None:
    """The refresh token issued last between the relay row (idx.feed_token, where it lives) and the env fallback (a
    re-login or a rotation invalidates the older one, so the newest ``iat`` is the only one worth trying)."""
    env = os.environ if env is None else env
    cands = [t for t in ((env.get(REFRESH_ENV) or "").strip(), _relay_refresh_token(conn)) if t]
    return max(cands, key=lambda t: _jwt_claim(t, "iat")) if cands else None


def refresh_and_persist(env: dict[str, str] | None = None, env_file: str | None = None,
                        poster: Poster | None = None, persist: bool = True,
                        conn: psycopg.Connection | None = None) -> str:
    """Refresh the access token from the newest refresh token (relay row, env as a fallback), store the new pair in
    ``idx.feed_token`` - the one place the tokens live since 2026-09-25 - and return the access token.

    The refresh token ROTATES: once Stockbit has issued the new pair the old refresh token is dead, so losing the new pair
    loses the session. The env file is therefore written only as an emergency copy when the database write fails."""
    env = os.environ if env is None else env
    rt = newest_refresh_token(env, conn)
    if not rt:
        raise BrokerAuthError("no Stockbit refresh token in idx.feed_token - paste the credentialStorage cookie at /idx/feed/relay")
    access, rotated, resp = refresh_access_token(rt, poster)
    if not persist:
        return access
    from .feed import store as feed_store
    try:
        fields = feed_store.parse_relay(resp if isinstance(resp, dict) else {})
    except ValueError:                                                        # an unfamiliar response shape: the pair we extracted
        fields = feed_store.parse_relay({"access_token": access, "refresh_token": rotated})
    try:
        if conn is not None:
            feed_store.save_token(conn, fields, source="refresh")
        else:
            from ..shared.db import get_connection
            with get_connection() as c:
                feed_store.save_token(c, fields, source="refresh")
    except (ValueError, psycopg.Error, OSError) as e:
        path = env_file or _default_env_file(env)
        logger.error("idx broker: refreshed token NOT stored in idx.feed_token (%s) - emergency copy to %s", e, path)
        if path:
            write_env_token(path, TOKEN_ENV, access)
            if rotated:
                write_env_token(path, REFRESH_ENV, rotated)
    return access


def minutes_needed(now: datetime, need_until: datetime | None, min_left_min: int) -> int:
    """Pure. How many minutes of validity the session must still have: the floor, or long enough to reach ``need_until``
    (the market close) - whichever is longer."""
    if need_until is None:
        return min_left_min
    return max(min_left_min, int((need_until - now).total_seconds() // 60))


def refresh_status(env: dict[str, str] | None = None, conn: psycopg.Connection | None = None,
                   now: datetime | None = None) -> dict[str, Any]:
    """The REFRESH token's own horizon (7 days, rotating). When it runs out nothing can be renewed headlessly and the
    operator has to paste the cookie again, so the guard watches it days ahead."""
    now = now or datetime.now(UTC)
    rt = newest_refresh_token(env, conn)
    if not rt:
        return {"present": False, "expires_at": None, "days_left": None}
    exp = _jwt_claim(rt, "exp")
    if not exp:
        return {"present": True, "expires_at": None, "days_left": None}
    when = datetime.fromtimestamp(exp, tz=UTC)
    return {"present": True, "expires_at": when, "days_left": (when - now).total_seconds() / 86400}


def renew_if_needed(conn: psycopg.Connection, env: dict[str, str] | None = None, *, min_left_min: int = 180,
                    need_until: datetime | None = None, force: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """Keep the Stockbit session alive for the tick feed, the gap-fade jobs and the broker snapshot: refresh when the
    newest access token (relay row or env) would run out before ``need_until`` (the market close) or has under
    ``min_left_min`` minutes left, and a refresh token is known. ``{renewed, minutes_left, needed, reason}``;
    raises BrokerFetchError when the refresh call itself fails."""
    from .feed import store as feed_store
    now = now or datetime.now(UTC)
    need = minutes_needed(now, need_until, min_left_min)
    st = feed_store.token_status(feed_store.load_token(conn), now)
    left = st.get("minutes_left")
    if not force and st["valid"] and left is not None and left > need:
        return {"renewed": False, "minutes_left": left, "needed": need, "reason": "fresh"}
    if not newest_refresh_token(env, conn):
        return {"renewed": False, "minutes_left": left, "needed": need, "reason": "no refresh token - paste the cookie at /idx/feed/relay"}
    access = refresh_and_persist(env, conn=conn)
    return {"renewed": True, "minutes_left": round((_jwt_claim(access, "exp") - time.time()) / 60), "needed": need, "reason": "renewed"}


def config_fresh(env: dict[str, str] | None = None, env_file: str | None = None,
                 conn: psycopg.Connection | None = None) -> dict[str, Any]:
    """``config()`` but, when a refresh token is known (env or relay row), refresh the access token first. Falls back
    to the stored access token if the refresh fails (a still-valid token keeps the run alive)."""
    explicit = env
    env = os.environ if env is None else env
    if newest_refresh_token(env, conn):
        try:
            refresh_and_persist(env, env_file, conn=conn)
        except BrokerFetchError as e:
            logger.warning("idx broker: token refresh failed, using the stored access token - %s", e)
    return config(explicit, conn=conn)
