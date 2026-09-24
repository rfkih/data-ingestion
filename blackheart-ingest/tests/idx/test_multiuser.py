"""Many users, each with their own desk: a signed-in account (Bearer session) sees and works only its books, tickets, journal,
watchlist and phones; an unscoped service caller (the CLI, the scheduler) sees every book; a service scoped with X-Idx-User (the
nightly agent) sees one account's; research writes are refused to accounts. Needs the local DB."""
from __future__ import annotations

import base64
import os
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from blackheart_ingest.idx import accounts as AC
from blackheart_ingest.idx import book, journal, notify, push, who

EMAILS = ("test-ana@multi.test", "test-budi@multi.test")


@pytest.fixture(scope="module")
def env():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        conn = psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    os.environ.setdefault("IDX_JWT_SECRET", base64.b64encode(b"t" * 48).decode())
    _clean(conn)
    users = {e: AC.create_user(conn, e, e.split("@")[0], None, "Correct-Horse-9!") for e in EMAILS}
    key = AC.secret()
    tokens = {e: AC.sign_token(u, key)[0] for e, u in users.items()}
    from blackheart_ingest.workers.server import app
    with TestClient(app) as client:
        yield {"conn": conn, "client": client, "users": users, "tokens": tokens}
    _clean(conn)
    conn.close()


def _clean(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM idx.app_user WHERE email = ANY(%s)", (list(EMAILS),))
        ids = [r["id"] for r in cur.fetchall()]
        if ids:
            cur.execute("SELECT book FROM idx.book WHERE owner_id = ANY(%s)", (ids,))
            books = [r["book"] for r in cur.fetchall()]
            for bk in books:
                cur.execute("DELETE FROM idx.ticket WHERE book = %s", (bk,))
                for t in ("book_mark", "book_nav", "position", "fill", "decision", "price_level"):
                    cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
                cur.execute("DELETE FROM idx.alert WHERE job IN (%s, %s)", (f"book:{bk}", f"ticket:{bk}"))
                cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
            cur.execute("DELETE FROM idx.decision WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM idx.watchlist WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM idx.push_device WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM idx.app_user WHERE id = ANY(%s)", (ids,))
    conn.commit()


def _as(env, email):
    return {"Authorization": f"Bearer {env['tokens'][email]}"}


def test_caller_kinds(env) -> None:
    c = env["client"]
    ana = _as(env, EMAILS[0])
    assert c.get("/idx/books").status_code == 200                                          # no credentials + no token configured = service
    r = c.get("/idx/books", headers={"Authorization": "Bearer nope.nope.nope"})
    assert r.status_code == 401 and "sign in" in r.json()["detail"]
    assert c.get("/idx/books", headers=ana).json() == []                                   # a new account: no books yet
    r = c.get("/idx/books", headers={"X-Idx-User": EMAILS[1]})                              # a service scoped to one account
    assert r.status_code == 200 and r.json() == []
    assert c.get("/idx/books", headers={"X-Idx-User": "nobody@multi.test"}).status_code == 401
    assert c.get("/idx/ops", headers={"X-Idx-Actor": "wizard"}).status_code == 400


def test_books_are_the_owners(env) -> None:
    c, conn = env["client"], env["conn"]
    ana, budi = _as(env, EMAILS[0]), _as(env, EMAILS[1])
    r = c.post("/idx/books", json={"label": "Trend", "kind": "live", "rule": "trend", "cash": 10_000_000, "broker": "stockbit",
                                   "fee_buy_pct": 0.10, "fee_sell_pct": 0.20}, headers=ana)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["book"].startswith("live-") and b["label"] == "Trend" and b["rule"] == "trend" and b["trend_variant"] == "small"
    assert b["owner_id"] == str(env["users"][EMAILS[0]]["id"]) and Decimal(b["max_weight_pct"]) == 15
    r2 = c.post("/idx/books", json={"label": "Paper", "kind": "paper", "cash": 100_000_000, "strategy": "strict", "max_names": 10}, headers=ana)
    assert r2.status_code == 200, r2.text
    p = r2.json()
    assert p["book"].startswith("paper-") and p["rule"] == "annual" and p["strategy"] == "strict"
    assert c.post("/idx/books", json={"label": "", "kind": "paper"}, headers=ana).status_code == 422
    assert c.post("/idx/books", json={"label": "x", "kind": "margin"}, headers=ana).status_code == 422
    assert c.post("/idx/books", json={"label": "x", "kind": "paper"}).status_code == 401                # a service has no account of its own

    mine = c.get("/idx/books", headers=ana).json()
    assert [x["book"] for x in mine] == [b["book"], p["book"]] and mine[0]["kind"] == "live" and mine[1]["label"] == "Paper"
    assert c.get("/idx/books", headers=budi).json() == []                                              # Budi sees none of Ana's
    assert c.get(f"/idx/book/{b['book']}", headers=budi).status_code == 404
    assert c.get(f"/idx/book/{b['book']}", headers=ana).status_code == 200
    assert c.get(f"/idx/book/{b['book']}").status_code == 200                                          # the desk's own tools see every book
    assert b["book"] in {x["book"] for x in c.get("/idx/books").json()}
    assert c.get(f"/idx/book/{b['book']}", headers={"X-Idx-User": EMAILS[0]}).status_code == 200
    assert c.get(f"/idx/book/{b['book']}", headers={"X-Idx-User": EMAILS[1]}).status_code == 404

    # settings, halt, fills, tickets, report: the owner's; a stranger gets 404 everywhere
    assert c.put(f"/idx/book/{p['book']}", json={"cash": 90_000_000}, headers=budi).status_code == 404
    assert Decimal(c.put(f"/idx/book/{p['book']}", json={"cash": 90_000_000, "label": "Paper strict"}, headers=ana).json()["cash"]) == 90_000_000
    assert c.post(f"/idx/book/{p['book']}/halt", json={"reason": "x"}, headers=budi).status_code == 404
    assert c.post(f"/idx/book/{p['book']}/fills", json={"trade_date": "2026-09-14", "code": "GJTL", "side": "buy", "lots": 10, "price": 1350},
                  headers=budi).status_code == 404
    assert c.post(f"/idx/book/{p['book']}/fills", json={"trade_date": "2026-09-14", "code": "GJTL", "side": "buy", "lots": 10, "price": 1350},
                  headers=ana).status_code == 200
    assert c.get("/idx/ticket/latest", params={"book": p["book"]}, headers=budi).status_code == 404
    assert c.get("/idx/report", params={"book": p["book"]}, headers=budi).status_code == 404
    assert c.get("/idx/report", params={"book": p["book"]}, headers=ana).status_code in (200, 422)

    # the journal: Ana's rows (hers and her books') are hers alone; a note lands in the writer's journal
    assert c.post("/idx/decision", json={"rationale": "my first note", "book": p["book"]}, headers=ana).status_code == 200
    assert c.post("/idx/decision", json={"rationale": "not my book", "book": p["book"]}, headers=budi).status_code == 404
    assert c.post("/idx/decision", json={"rationale": "budi's own note"}, headers=budi).status_code == 200
    ana_rows = c.get("/idx/decision", headers=ana).json()
    assert {r["action"] for r in ana_rows} >= {"note", "settings", "fill"} and all(r["book"] in (None, b["book"], p["book"]) for r in ana_rows)
    assert not any(r["rationale"] == "budi's own note" for r in ana_rows)
    budi_rows = c.get("/idx/decision", headers=budi).json()
    assert [r["rationale"] for r in budi_rows] == ["budi's own note"]
    assert any(r["rationale"] == "budi's own note" for r in c.get("/idx/decision").json())              # the desk sees all
    assert journal.recent(conn, user_id=str(env["users"][EMAILS[1]]["id"]))[0]["rationale"] == "budi's own note"

    # alerts on a book reach only its owner's list (and the desk's)
    from blackheart_ingest.idx import runlog
    runlog.alert(conn, "warning", f"book:{p['book']}", "held X broke the gate")
    assert any(a["job"] == f"book:{p['book']}" for a in c.get("/idx/alerts", headers=ana).json())
    assert not any(a["job"] == f"book:{p['book']}" for a in c.get("/idx/alerts", headers=budi).json())
    assert not any(a["job"] == f"book:{p['book']}" for a in c.get("/idx/ops", headers=budi).json()["open_alerts"])

    # closing a book: out of the list, history kept
    assert c.delete(f"/idx/book/{b['book']}", headers=budi).status_code == 404
    r = c.delete(f"/idx/book/{b['book']}", headers=ana)
    assert r.status_code == 200 and r.json()["archived_at"]
    assert [x["book"] for x in c.get("/idx/books", headers=ana).json()] == [p["book"]]
    assert b["book"] in {x["book"] for x in c.get("/idx/books", params={"archived": 1}, headers=ana).json()}
    assert b["book"] not in book.list_books(conn) and b["book"] not in book.list_books(conn, str(env["users"][EMAILS[0]]["id"]))


def test_watchlist_and_phones_are_per_account(env) -> None:
    c, conn = env["client"], env["conn"]
    ana, budi = _as(env, EMAILS[0]), _as(env, EMAILS[1])
    assert c.put("/idx/watchlist", json=[{"code": "gjtl", "note": "tyres"}], headers=ana).json()["codes"] == ["GJTL"]
    assert c.put("/idx/watchlist", json=[{"code": "BBCA"}], headers=budi).json()["codes"] == ["BBCA"]
    assert [w["code"] for w in c.get("/idx/watchlist", headers=ana).json()] == ["GJTL"]
    assert [w["code"] for w in c.get("/idx/watchlist", headers=budi).json()] == ["BBCA"]
    assert c.get("/idx/watchlist").json() == [] and c.put("/idx/watchlist", json=[]).status_code == 401

    tok_a, tok_b = "test-device-ana-" + "a" * 24, "test-device-budi-" + "b" * 24
    assert c.post("/idx/push/register", json={"token": tok_a, "label": "Ana's phone"}).status_code == 401       # a phone belongs to an account
    assert c.post("/idx/push/register", json={"token": tok_a, "label": "Ana's phone"}, headers=ana).json()["user_id"] == str(env["users"][EMAILS[0]]["id"])
    assert c.post("/idx/push/register", json={"token": tok_b}, headers=budi).status_code == 200
    assert [d["label"] for d in c.get("/idx/push/devices", headers=ana).json()["devices"]] == ["Ana's phone"]
    assert len(c.get("/idx/push/devices", headers=budi).json()["devices"]) == 1
    assert c.delete(f"/idx/push/{tok_a}", headers=budi).json()["removed"] is False                          # not Budi's to forget
    assert {d["token"] for d in push.devices(conn, user_id=str(env["users"][EMAILS[0]]["id"]))} == {tok_a}
    # the phone moves with the sign-in: Budi signs in on Ana's phone
    assert c.post("/idx/push/register", json={"token": tok_a}, headers=budi).json()["user_id"] == str(env["users"][EMAILS[1]]["id"])
    assert c.get("/idx/push/devices", headers=ana).json()["devices"] == []
    assert c.delete(f"/idx/push/{tok_a}", headers=budi).json()["removed"] is True
    assert c.delete(f"/idx/push/{tok_b}", headers=budi).json()["removed"] is True


def test_notify_targets_the_owner(env, monkeypatch) -> None:
    conn = env["conn"]
    uid_a = str(env["users"][EMAILS[0]]["id"])
    bk = book.create_book(conn, uid_a, "paper", "Notify test", cash=1_000_000)
    monkeypatch.setenv(push.SA_ENV, __file__)                                                          # "configured": the file exists
    monkeypatch.delenv(notify.TOKEN_ENV, raising=False)
    monkeypatch.delenv(notify.OPS_ENV, raising=False)
    got = []
    monkeypatch.setattr(push, "broadcast", lambda t, b, d=None, sender=None, user_id=None: got.append((t, user_id)) or {"sent": 1})
    assert notify.send("hello\nbody", book=bk) and got[-1] == ("hello", uid_a)                          # the book's owner
    assert notify.send("direct", user_id="someone") and got[-1][1] == "someone"
    assert notify.send("nobody's", book="no-such-book") is False and len(got) == 2                     # no target: dropped
    monkeypatch.setenv(notify.OPS_ENV, EMAILS[1])
    assert notify.send("desk alert") and got[-1][1] == str(env["users"][EMAILS[1]]["id"])              # the ops account
    assert notify.on_alert("critical", f"book:{bk}", "stop hit") and got[-1][1] == uid_a
    assert notify.on_alert("warning", "daily", "no bar") and got[-1][1] == str(env["users"][EMAILS[1]]["id"])
    book.archive(conn, bk)


def test_research_writes_are_the_desks_only(env) -> None:
    c = env["client"]
    ana = _as(env, EMAILS[0])
    assert c.post("/idx/pack/build", headers=ana).status_code == 403
    assert c.post("/idx/name/GJTL/evidence", json={"kind": "news", "title": "x"}, headers=ana).status_code == 403
    assert c.post("/idx/macro/pull", json={}, headers=ana).status_code == 403
    assert c.post("/idx/overlay/check", json={"dry_run": True}, headers=ana).status_code == 403


def test_own_book_helper(env) -> None:
    conn = env["conn"]
    uid_a, uid_b = (str(env["users"][e]["id"]) for e in EMAILS)
    bk = book.create_book(conn, uid_a, "paper", "Helper", cash=1)
    ana = who.Caller("operator", uid_a, EMAILS[0], False)
    budi = who.Caller("operator", uid_b, EMAILS[1], False)
    desk = who.Caller("scheduler", None, None, True)
    assert who.own_book(conn, bk, ana)["label"] == "Helper" and who.own_book(conn, bk, desk)["book"] == bk
    with pytest.raises(Exception, match="no book"):
        who.own_book(conn, bk, budi)
    with pytest.raises(Exception, match="no book"):
        who.own_book(conn, "no-such-book", desk)
    book.archive(conn, bk)


def test_one_persons_alerts_and_preferences_are_their_own(env) -> None:
    """Phase 4 scoping: the bus is shared, the reading of it is not."""
    c, conn = env["client"], env["conn"]
    ana, budi = EMAILS
    ana_id, budi_id = str(env["users"][ana]["id"]), str(env["users"][budi]["id"])
    from blackheart_ingest.idx import runlog
    mine = runlog.alert(conn, "info", "test:scope", "for ana", kind="signal", strategy="trend_small",
                        user_id=ana_id, notify_channels=False)
    theirs = runlog.alert(conn, "info", "test:scope", "for budi", kind="signal", strategy="trend_small",
                          user_id=budi_id, notify_channels=False)
    desk = runlog.alert(conn, "warning", "test:scope", "for the desk", kind="feed", notify_channels=False)
    try:
        seen = {a["id"] for a in c.get("/idx/alerts?limit=200", headers=_as(env, ana)).json()}
        assert mine in seen and desk in seen and theirs not in seen
        assert {a["id"] for a in c.get("/idx/alerts?limit=200&kind=feed", headers=_as(env, ana)).json()} == {desk}
        assert all(a["id"] > mine for a in c.get(f"/idx/alerts?limit=200&since={mine}", headers=_as(env, ana)).json())

        # preferences are per person, and unmuting removes the row rather than storing a false
        assert c.get("/idx/alerts/prefs", headers=_as(env, ana)).json()["prefs"] == []
        assert c.put("/idx/alerts/prefs", json={"kind": "signal", "muted": True}, headers=_as(env, ana)).status_code == 200
        assert [p["kind"] for p in c.get("/idx/alerts/prefs", headers=_as(env, ana)).json()["prefs"]] == ["signal"]
        assert c.get("/idx/alerts/prefs", headers=_as(env, budi)).json()["prefs"] == []
        assert c.put("/idx/alerts/prefs", json={"kind": "nonsense", "muted": True},
                     headers=_as(env, ana)).status_code == 422
        c.put("/idx/alerts/prefs", json={"kind": "signal", "muted": False}, headers=_as(env, ana))
        assert c.get("/idx/alerts/prefs", headers=_as(env, ana)).json()["prefs"] == []

        # a mute stops the phone, never the record: the row is still on the bus for that person to read
        from blackheart_ingest.idx import prefs as P
        P.set_pref(conn, ana_id, kind="signal", muted=True)
        assert P.allows(conn, ana_id, "signal") is False
        assert mine in {a["id"] for a in c.get("/idx/alerts?limit=200", headers=_as(env, ana)).json()}
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM idx.alert WHERE job = 'test:scope'")
            cur.execute("DELETE FROM idx.alert_pref WHERE user_id = ANY(%s)", ([ana_id, budi_id],))
        conn.commit()
