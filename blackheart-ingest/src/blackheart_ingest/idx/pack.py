"""The analysis pack — one markdown document the operator pastes into Claude chat (no API spend), and the
importer for the JSON answer that comes back.

Names in a pack = the selected candidates (+ the next ``next_n`` in rank) plus the watchlist (where held names live until
the position book exists). Every figure is point-in-time as of the pack date: fundamentals by IDX ``File_Modified``,
disclosures by ``TglPengumuman``. The pinned prompt is versioned (``PROMPT_VERSION``); answers are stored in
``idx.nightly_pack.answer_json`` and as ``idx.sentiment_score`` rows (``doc_type='pack'``, ``model='claude-chat-manual'``)
so the operator's judgment is logged and can be reviewed against outcomes later.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
import psycopg.types.json

from . import candidates as cand
from .card import _pct, _rows, _t, _x
from .metrics import fundamentals_asof

logger = logging.getLogger(__name__)
PROMPT_VERSION = "pack_v1"
WIB = ZoneInfo("Asia/Jakarta")
STANCES = {"buy": 2, "hold": 0, "avoid": -1, "sell": -2}
QUIET_KINDS = ("registry", "ad_proof", "other", "ipo_proceeds", "exploration", "listing_change", "prospectus", "financial_report")

PROMPT = """\
# Instructions (pinned, {version})

You are the second reader for a small, long-only Indonesian equity book run by one person. The book follows a rule that was
tested point-in-time 2021-2026: profitable companies (audited net profit > 0, ROE >= 5 %) ranked by a composite of earnings
yield, book yield and dividend yield; the top fifth is held equal-weight for a year and rebalanced each May. The rule has
worked on cheapness alone; the person's job - and yours here - is to catch the individual names where cheapness is a trap:
structurally shrinking revenue, profits that exist only on paper (negative operating cash flow, one-off gains, mark-to-market
of a holding company), leverage that is rising, governance events (exchange queries, affiliated transactions, changes of
control, auditor changes), or a dividend that is about to be cut.

Rules for your answer:
1. Use only what is in this pack. Do not bring in outside knowledge of prices or news after the pack date, and do not speculate
   about future prices. If the pack lacks what you need to judge a name, say so in `risks` and keep conviction low.
2. The strict-gate failures and warnings are inputs, not verdicts. A bank failing "D/E" or a cyclical with one bad year can still
   be fine; a company passing every gate can still be a trap.
3. Be specific: name the figure or disclosure that drives your view.
4. Answer ONLY with one JSON block in exactly this shape (no prose before or after):

```json
{{"pack_date": "{pack_date}", "prompt_version": "{version}",
 "names": [
  {{"code": "XXXX", "stance": "buy|hold|avoid|sell", "conviction": 1, "thesis": "one or two sentences",
   "risks": "the specific thing that would make this a value trap", "veto": false, "veto_reason": null}}
 ],
 "notes": "anything that applies to the whole list (sector concentration, market context)"}}
```
`stance`: buy = add or initiate at the rebalance; hold = keep if held, do not add; avoid = do not buy even though the rule
selects it; sell = exit if held. `conviction` 1 (weak) to 5 (strong). `veto: true` only when you would overrule the rule for
a selected name - then `veto_reason` is mandatory.
"""


def _price_stats(conn: psycopg.Connection, code: str, D: date) -> dict[str, Any]:
    rows = _rows(conn, """
        SELECT trade_date, close * adj_factor AS c FROM idx.bar WHERE code = %s AND source IN ('idx', 'yahoo') AND trade_date <= %s
         ORDER BY trade_date DESC LIMIT 260""", (code, D), ["d", "c"])
    if not rows:
        return {}
    c = [Decimal(r["c"]) for r in rows]
    last = c[0]

    def chg(n: int):
        return (last / c[n] - 1) if len(c) > n and c[n] > 0 else None

    hi, lo = max(c), min(c)
    return {"chg_1m": chg(21), "chg_3m": chg(63), "chg_12m": chg(min(len(c) - 1, 250)), "hi_52w": hi, "lo_52w": lo,
            "pos_52w": ((last - lo) / (hi - lo)) if hi > lo else None}


def _flow(conn: psycopg.Connection, code: str, D: date) -> dict[str, Any]:
    rows = _rows(conn, """
        SELECT foreign_buy - foreign_sell AS net, volume, close FROM idx.daily_summary WHERE code = %s AND trade_date <= %s
         ORDER BY trade_date DESC LIMIT 20""", (code, D), ["net", "vol", "close"])
    net = sum(int(r["net"] or 0) for r in rows)
    vol = sum(int(r["vol"] or 0) for r in rows)
    val = sum(int(r["net"] or 0) * float(r["close"] or 0) for r in rows)
    return {"net20_shares": net, "net20_share_of_volume": (net / vol) if vol else None, "net20_value": val}


def _disclosures(conn: psycopg.Connection, code: str, since: datetime, until: date, limit: int = 8) -> tuple[list[dict], dict]:
    rows = _rows(conn, """
        SELECT published_at, kind, title FROM idx.announcement
         WHERE code = %s AND published_at > %s AND published_at < %s AND kind <> ALL(%s)
         ORDER BY published_at DESC""", (code, since, until + timedelta(days=1), list(QUIET_KINDS)), ["pub", "kind", "title"])
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    return rows[:limit], kinds


def _fund_rows(conn: psycopg.Connection, code: str, D: date) -> list[dict[str, Any]]:
    rows = _rows(conn, """
        SELECT period_end, period_label, published_at, revenue, net_profit, revenue_yoy, net_profit_yoy, roe, der, cfo, total_equity,
               dividends_paid
          FROM idx.fundamental WHERE code = %s AND published_at <= %s ORDER BY period_end DESC, published_at DESC""",
        (code, D + timedelta(days=1)), ["pe", "label", "pub", "rev", "np", "rev_yoy", "np_yoy", "roe", "der", "cfo", "eq", "div"])
    q = [r for r in rows if r["label"] != "TAHUNAN"][:4]
    a = [r for r in rows if r["label"] == "TAHUNAN"][:3]
    return sorted(q + a, key=lambda r: (r["pe"], r["label"] == "TAHUNAN"), reverse=True)


def _name_section(conn: psycopg.Connection, code: str, D: date, since: datetime, crow: dict[str, Any] | None,
                  m: dict[str, Any] | None, listing: dict[str, Any], watch_note: str | None) -> tuple[str, dict[str, Any]]:
    px = _rows(conn, """
        SELECT b.close * b.adj_factor AS close, s.listed_shares, f.value_60d_median
          FROM idx.bar b JOIN idx.daily_summary s USING (trade_date, code) LEFT JOIN idx.feature_daily f USING (trade_date, code)
         WHERE b.code = %s AND b.source IN ('idx', 'yahoo') AND b.trade_date <= %s ORDER BY b.trade_date DESC LIMIT 1""", (code, D),
        ["close", "shares", "v60"])
    p = px[0] if px else {"close": None, "shares": None, "v60": None}
    price = Decimal(p["close"]) if p["close"] else None
    mcap = (price * Decimal(p["shares"])) if (price and p["shares"]) else None
    ps, fl = _price_stats(conn, code, D), _flow(conn, code, D)
    disc, kinds = _disclosures(conn, code, since, D)
    fr = _fund_rows(conn, code, D)
    acts = _rows(conn, "SELECT ex_date, kind, factor FROM idx.corporate_action WHERE code = %s AND ex_date <= %s ORDER BY ex_date DESC LIMIT 2",
                 (code, D), ["ex_date", "kind", "factor"])
    ep = (m["net_profit"] / mcap) if (m and m.get("net_profit") is not None and mcap) else None
    ep_ttm = (m["net_profit_ttm"] / mcap) if (m and m.get("net_profit_ttm") is not None and mcap) else None
    bp = (m["equity"] / mcap) if (m and m.get("equity") is not None and mcap) else None
    dy = crow["dy"] if crow else None
    o = [f"### {code} - {listing.get('name') or ''}"]
    tag = []
    if crow:
        tag.append(f"candidate rank {crow['rank']}{' (SELECTED)' if crow['selected'] else ''}")
    if watch_note is not None:
        tag.append(f"watchlist: {watch_note or 'no note'}")
    o.append(f"{listing.get('sector') or '?'} / {listing.get('subsector') or '?'} | {' | '.join(tag) if tag else 'not a candidate'}")
    o.append(f"- price Rp {float(price):,.0f} | mcap Rp {_t(mcap)} T | 60d median value Rp {_t(p['v60'], 1e9, 1)} bn/day | "
             f"1m {_pct(ps.get('chg_1m'))} 3m {_pct(ps.get('chg_3m'))} 12m {_pct(ps.get('chg_12m'))} | 52w range position {_pct(ps.get('pos_52w'), 0)}"
             if price else "- no price")
    if m:
        pe = (1 / ep) if ep and ep > 0 else None
        pe_ttm = (1 / ep_ttm) if ep_ttm and ep_ttm > 0 else None
        o.append(f"- P/E {_x(pe, 1)} (audited FY{m['annual_period'].year if m['annual_period'] else '?'}) | P/E ttm {_x(pe_ttm, 1)} ({m.get('ttm_basis') or '-'}) | "
                 f"P/B {_x((1 / bp) if bp else None)} | dividend yield {_pct(dy)} | ROE {_pct(m['roe'])} | D/E {'financial' if m.get('is_financial') else _x(m['der'])}")
        o.append(f"- book rule (profit>0, ROE>=5%): {'PASS' if m['gate_loose'] else 'FAIL'} | strict gate: "
                 f"{'PASS' if m['gate_strict'] else 'fail: ' + ', '.join(m['strict_fails'])} | warnings: {', '.join(m['warnings']) or 'none'}")
    else:
        o.append("- no audited report in hand")
    if fr:
        o.append("")
        o.append("| period | published | revenue T | yoy | net profit T | yoy | ROE | D/E | CFO T | div paid T |")
        o.append("|---|---|---|---|---|---|---|---|---|---|")
        for f in fr:
            lab = f"FY{f['pe'].year}" if f["label"] == "TAHUNAN" else f"{f['label']} {f['pe'].year}"
            o.append(f"| {lab} | {f['pub'].date()} | {_t(f['rev'])} | {_pct(f['rev_yoy'], 0)} | {_t(f['np'], 1e12, 3)} | {_pct(f['np_yoy'], 0)} | "
                     f"{_pct(f['roe'])} | {_x(f['der'])} | {_t(f['cfo'])} | {_t(f['div'])} |")
    o.append("")
    o.append(f"- foreign flow 20d: net {fl['net20_shares'] / 1e6:+,.1f} M shares ({_pct(fl['net20_share_of_volume'])} of volume), "
             f"~Rp {fl['net20_value'] / 1e9:+,.1f} bn")
    if acts:
        o.append("- corporate actions: " + "; ".join(f"{a['ex_date']} {a['kind']} x{float(a['factor']):.4g}" for a in acts))
    if disc:
        o.append(f"- disclosures since {since.astimezone(WIB).date()} ({', '.join(f'{k} {n}' for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))}):")
        for d in disc:
            o.append(f"  - {d['pub'].astimezone(WIB).date()} [{d['kind']}] {(d['title'] or '')[:140]}")
    else:
        o.append(f"- no material disclosures since {since.astimezone(WIB).date()}")
    o.append("")
    j = {"code": code, "name": listing.get("name"), "sector": listing.get("sector"), "price": price, "mcap": mcap,
         "candidate_rank": crow["rank"] if crow else None, "selected": bool(crow and crow["selected"]), "watch_note": watch_note,
         "ep": ep, "ep_ttm": ep_ttm, "bp": bp, "dy": dy,
         "roe": m["roe"] if m else None, "der": m["der"] if m else None, "gate_loose": bool(m and m["gate_loose"]),
         "gate_strict": bool(m and m["gate_strict"]), "strict_fails": m["strict_fails"] if m else [], "warnings": m["warnings"] if m else [],
         "ttm_basis": m.get("ttm_basis") if m else None, **ps, **fl, "disclosure_kinds": kinds,
         "disclosures": [{"date": d["pub"].astimezone(WIB).date(), "kind": d["kind"], "title": d["title"]} for d in disc]}
    return "\n".join(o), j


def _market(conn: psycopg.Connection, D: date) -> str:
    rows = _rows(conn, """
        SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date <= %s
         ORDER BY trade_date DESC LIMIT 260""", (D,), ["d", "c"])
    if not rows:
        return "- COMPOSITE: no index data"
    c = [Decimal(r["c"]) for r in rows]

    def chg(n):
        return _pct(c[0] / c[n] - 1) if len(c) > n else "-"

    return f"- COMPOSITE {float(c[0]):,.0f} on {rows[0]['d']} | 1m {chg(21)} | 3m {chg(63)} | 12m {chg(min(len(c) - 1, 250))}"


def build(conn: psycopg.Connection, as_of: date | None = None, *, next_n: int = 10, codes: list[str] | None = None) -> dict[str, Any]:
    """Build the pack for the latest candidate run on/before as_of (running the candidate list first if needed)."""
    run = _rows(conn, "SELECT max(run_date) FROM idx.candidate WHERE (%s::date IS NULL OR run_date <= %s)", (as_of, as_of), ["d"])[0]["d"]
    last_bar = _rows(conn, "SELECT max(trade_date) FROM idx.bar WHERE source IN ('idx', 'yahoo') AND (%s::date IS NULL OR trade_date <= %s)",
                     (as_of, as_of), ["d"])[0]["d"]
    if run is None or (last_bar and run < last_bar):
        res = cand.build(conn, as_of)
        cand.store(conn, res)
        run = res["as_of"]
    D: date = run
    crows = _rows(conn, """
        SELECT code, rank, selected, score, ep, bp, dy, ep_ttm, roe, der, gate_strict, strict_fails, warnings, f20, ttm_basis
          FROM idx.candidate WHERE run_date = %s ORDER BY rank""", (D,),
        ["code", "rank", "selected", "score", "ep", "bp", "dy", "ep_ttm", "roe", "der", "gate_strict", "strict_fails", "warnings", "f20", "ttm_basis"])
    by_code = {r["code"]: r for r in crows}
    n_sel = sum(1 for r in crows if r["selected"])
    listed = [r["code"] for r in crows[: n_sel + next_n]]
    watch = {w["code"]: w["note"] for w in _rows(conn, "SELECT code, note FROM idx.watchlist ORDER BY code", (), ["code", "note"])}
    names = codes or (listed + [c for c in watch if c not in listed])
    prev = _rows(conn, "SELECT max(pack_date) FROM idx.nightly_pack WHERE pack_date < %s", (D,), ["d"])[0]["d"]
    since = datetime.combine(prev or (D - timedelta(days=14)), datetime.min.time(), tzinfo=WIB).replace(hour=16)
    fund = fundamentals_asof(conn, D, names)
    listings = {r["code"]: r for r in _rows(conn, "SELECT code, name, sector, subsector FROM idx.listing WHERE code = ANY(%s)", (names,),
                                            ["code", "name", "sector", "subsector"])}
    o = [PROMPT.format(version=PROMPT_VERSION, pack_date=D.isoformat()), "", f"# Pack {D} (data as of the {D} close; previous pack {prev or 'none'})", "",
         "## Market", _market(conn, D), "",
         f"## Candidate list ({D}): {n_sel} selected of {len(crows)} in the loose-gate pool; next {min(next_n, max(0, len(crows) - n_sel))} shown for context",
         "| # | code | E/P | E/P ttm | P/B | DY | ROE | D/E | flow20 | strict gate | warnings |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in crows[: n_sel + next_n]:
        o.append(f"| {r['rank']}{'*' if r['selected'] else ''} | {r['code']} | {_pct(r['ep'])} | {_pct(r['ep_ttm'])} | "
                 f"{_x((1 / Decimal(r['bp'])) if r['bp'] else None)} | {_pct(r['dy'])} | {_pct(r['roe'])} | {_x(r['der'])} | {_pct(r['f20'])} | "
                 f"{'PASS' if r['gate_strict'] else 'fail: ' + ','.join(r['strict_fails'] or [])} | {','.join(r['warnings'] or []) or '-'} |")
    if watch:
        o += ["", "## Watchlist / held names", ", ".join(f"{c}{' (' + n + ')' if n else ''}" for c, n in watch.items())]
    o += ["", "## Names", ""]
    names_json = []
    for code in names:
        md, j = _name_section(conn, code, D, since, by_code.get(code), fund.get(code), listings.get(code, {}), watch.get(code) if code in watch else None)
        o.append(md)
        names_json.append(j)
    o += ["## Answer", "", f"Return the JSON block described in the instructions, one entry per name above ({len(names)} names), pack_date \"{D}\"."]
    md = "\n".join(o)
    pj = {"pack_date": D.isoformat(), "prompt_version": PROMPT_VERSION, "previous_pack": prev.isoformat() if prev else None,
          "since": since.isoformat(), "generated_at": datetime.now(UTC).isoformat(), "selected": n_sel, "pool": len(crows),
          "codes": names, "names": names_json}
    return {"pack_date": D, "prompt_version": PROMPT_VERSION, "md": md, "json": pj, "codes": names}


def store(conn: psycopg.Connection, pack: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO idx.nightly_pack (pack_date, prompt_version, pack_md, pack_json, generated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (pack_date) DO UPDATE SET prompt_version = EXCLUDED.prompt_version, pack_md = EXCLUDED.pack_md,
                pack_json = EXCLUDED.pack_json, generated_at = now()
            """, (pack["pack_date"], pack["prompt_version"], pack["md"], psycopg.types.json.Jsonb(json.loads(json.dumps(pack["json"], default=str)))))
    conn.commit()


def load(conn: psycopg.Connection, pack_date: date | None = None) -> dict[str, Any] | None:
    rows = _rows(conn, """
        SELECT pack_date, prompt_version, pack_md, pack_json, generated_at, answer_json, imported_at FROM idx.nightly_pack
         WHERE (%s::date IS NULL OR pack_date = %s) ORDER BY pack_date DESC LIMIT 1""", (pack_date, pack_date),
        ["pack_date", "prompt_version", "pack_md", "pack_json", "generated_at", "answer_json", "imported_at"])
    return rows[0] if rows else None


class AnswerError(ValueError):
    pass


def validate_answer(answer: Any, pack_codes: list[str], pack_date: date) -> dict[str, Any]:
    """Pure: the JSON block from Claude chat -> normalised answer. Raises AnswerError with every problem listed."""
    if isinstance(answer, str):
        s = answer.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else ""
            s = s.rsplit("```", 1)[0]
        try:
            answer = json.loads(s)
        except json.JSONDecodeError as e:
            raise AnswerError(f"not valid JSON: {e}") from None
    if not isinstance(answer, dict) or not isinstance(answer.get("names"), list):
        raise AnswerError("expected an object with a 'names' list")
    errs: list[str] = []
    if str(answer.get("pack_date") or "") != pack_date.isoformat():
        errs.append(f"pack_date {answer.get('pack_date')!r} != {pack_date}")
    out, seen = [], set()
    for i, n in enumerate(answer["names"]):
        if not isinstance(n, dict):
            errs.append(f"names[{i}]: not an object")
            continue
        code = str(n.get("code") or "").upper().strip()
        stance = str(n.get("stance") or "").lower().strip()
        conv = n.get("conviction")
        veto = bool(n.get("veto"))
        if code not in pack_codes:
            errs.append(f"{code or f'names[{i}]'}: not in the pack")
        if code in seen:
            errs.append(f"{code}: duplicate")
        seen.add(code)
        if stance not in STANCES:
            errs.append(f"{code}: stance {stance!r} not one of {sorted(STANCES)}")
        if not isinstance(conv, int) or not 1 <= conv <= 5:
            errs.append(f"{code}: conviction must be an integer 1..5")
        if veto and not (n.get("veto_reason") or "").strip():
            errs.append(f"{code}: veto without veto_reason")
        if not (n.get("thesis") or "").strip():
            errs.append(f"{code}: empty thesis")
        out.append({"code": code, "stance": stance, "conviction": conv, "thesis": (n.get("thesis") or "").strip(),
                    "risks": (n.get("risks") or "").strip(), "veto": veto, "veto_reason": (n.get("veto_reason") or None)})
    missing = [c for c in pack_codes if c not in seen]
    if errs:
        raise AnswerError("; ".join(errs))
    return {"pack_date": pack_date.isoformat(), "prompt_version": str(answer.get("prompt_version") or PROMPT_VERSION),
            "names": out, "notes": (answer.get("notes") or "").strip(), "missing": missing}


def import_answer(conn: psycopg.Connection, pack_date: date, answer: Any, model: str = "claude-chat-manual") -> dict[str, Any]:
    """Store an answer under ``model`` (``claude-chat-manual`` = pasted from chat; the MCP tools send ``claude-code``).
    The conflict key includes the model, so a manual and an agent answer coexist per pack date."""
    p = load(conn, pack_date)
    if p is None:
        raise AnswerError(f"no pack for {pack_date}")
    codes = list((p["pack_json"] or {}).get("codes") or [])
    a = validate_answer(answer, codes, pack_date)
    now = datetime.now(UTC)
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO idx.sentiment_score (doc_type, doc_id, code, model, prompt_version, event_type, stance, materiality, confidence,
                                             rationale, veto, scored_at)
            VALUES ('pack', %(doc_id)s, %(code)s, %(model)s, %(pv)s, %(stance_word)s, %(stance)s, NULL, %(conf)s, %(rationale)s,
                    %(veto)s, %(now)s)
            ON CONFLICT (doc_type, doc_id, code, model, prompt_version) DO UPDATE SET event_type = EXCLUDED.event_type,
                stance = EXCLUDED.stance, confidence = EXCLUDED.confidence, rationale = EXCLUDED.rationale, veto = EXCLUDED.veto,
                scored_at = EXCLUDED.scored_at
            """,
            [{"doc_id": pack_date.isoformat(), "code": n["code"], "model": model, "pv": a["prompt_version"], "stance_word": n["stance"],
              "stance": STANCES[n["stance"]], "conf": Decimal(n["conviction"]) / 5,
              "rationale": n["thesis"] + ((" | risks: " + n["risks"]) if n["risks"] else "") + ((" | VETO: " + n["veto_reason"]) if n["veto"] else ""),
              "veto": "skip" if n["veto"] else None, "now": now} for n in a["names"]])
        cur.execute("UPDATE idx.nightly_pack SET answer_json = %s, imported_at = %s WHERE pack_date = %s",
                    (psycopg.types.json.Jsonb(a), now, pack_date))
    conn.commit()
    return a


def answers(conn: psycopg.Connection, code: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _rows(conn, """
        SELECT doc_id AS pack_date, code, event_type AS stance, confidence * 5 AS conviction, veto, rationale, scored_at
          FROM idx.sentiment_score WHERE doc_type = 'pack' AND (%s::text IS NULL OR code = %s)
         ORDER BY scored_at DESC, code LIMIT %s""", (code, code, limit), ["pack_date", "code", "stance", "conviction", "veto", "rationale", "scored_at"])


HORIZONS = (21, 63, 126, 252)


def score_answers(conn: psycopg.Connection, horizons: tuple[int, ...] = HORIZONS) -> dict[str, Any]:
    """Forward price returns after each imported answer (from the pack-date close), per stance and for vetoes, and the
    excess over the COMPOSITE across the same days — the ledger that says whether the second reader adds to the rule or
    subtracts from it. Answers younger than a horizon simply do not count at that horizon."""
    import bisect
    rows = _rows(conn, """
        SELECT doc_id AS pack_date, code, event_type AS stance, veto FROM idx.sentiment_score
         WHERE doc_type = 'pack' ORDER BY doc_id, code""", (), ["pack_date", "code", "stance", "veto"])
    ix = {r["d"]: Decimal(r["c"]) for r in _rows(conn, "SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' ORDER BY 1",
                                                 (), ["d", "c"])}
    ix_days = sorted(ix)
    scored = []
    for r in rows:
        D = date.fromisoformat(r["pack_date"])
        px = _rows(conn, """SELECT trade_date, close * adj_factor AS c FROM idx.bar WHERE code = %s AND source IN ('idx', 'yahoo') AND trade_date >= %s
                            ORDER BY trade_date LIMIT %s""", (r["code"], D, max(horizons) + 1), ["d", "c"])
        if not px or not px[0]["c"]:
            continue
        base = Decimal(px[0]["c"])
        i0 = bisect.bisect_left(ix_days, px[0]["d"])
        rec: dict[str, Any] = {"pack_date": r["pack_date"], "code": r["code"], "stance": r["stance"], "veto": bool(r["veto"])}
        for h in horizons:
            if len(px) > h:
                rec[f"ret_{h}"] = float(Decimal(px[h]["c"]) / base - 1)
                if i0 + h < len(ix_days) and i0 < len(ix_days):
                    rec[f"xs_{h}"] = rec[f"ret_{h}"] - float(ix[ix_days[i0 + h]] / ix[ix_days[i0]] - 1)
        scored.append(rec)
    groups: dict[str, dict[int, dict[str, float]]] = {}
    for rec in scored:
        for g in (rec["stance"], *(("veto",) if rec["veto"] else ())):
            for h in horizons:
                if f"ret_{h}" in rec:
                    s = groups.setdefault(g, {}).setdefault(h, {"n": 0, "sum": 0.0, "hits": 0, "xs": 0.0, "xs_n": 0})
                    s["n"] += 1
                    s["sum"] += rec[f"ret_{h}"]
                    s["hits"] += rec[f"ret_{h}"] > 0
                    if f"xs_{h}" in rec:
                        s["xs"] += rec[f"xs_{h}"]
                        s["xs_n"] += 1
    return {"answers": len(rows), "scored": len(scored), "horizons": list(horizons), "groups": groups, "rows": scored}


def render_scores(s: dict[str, Any]) -> str:
    o = [f"# Pack answers vs forward returns ({s['scored']} of {s['answers']} answers have prices after the pack date)", "",
         "| stance | horizon (trading days) | n | avg return | hit rate | avg excess vs COMPOSITE |", "|---|---|---|---|---|---|"]
    n_lines = 0
    for g in ("buy", "hold", "avoid", "sell", "veto"):
        for h in s["horizons"]:
            v = s["groups"].get(g, {}).get(h)
            if v:
                xs = f"{100 * v['xs'] / v['xs_n']:+.1f}%" if v["xs_n"] else "-"
                o.append(f"| {g} | {h} | {v['n']} | {100 * v['sum'] / v['n']:+.1f}% | {100 * v['hits'] / v['n']:.0f}% | {xs} |")
                n_lines += 1
    if not n_lines:
        o.append("| (no answer is old enough for the shortest horizon yet) | | | | | |")
    return "\n".join(o)
