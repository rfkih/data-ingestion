"""The notification rule (idx/alert_policy.py): stock actions and system errors that need a person, nothing else."""
from __future__ import annotations

import pytest

from blackheart_ingest.idx import alert_policy as ap


def row(severity: str, job: str, message: str, kind: str | None = None, strategy: str | None = None) -> dict:
    return {"severity": severity, "job": job, "message": message, "kind": kind, "strategy": strategy}


@pytest.mark.parametrize("r", [
    row("warning", "ticket:live-fae554", "combo ticket #12 not issued - cash"),
    row("warning", "risk:trend_live", "trend_live risk: 1-day VaR99 5.0 % > 4 %", kind="risk"),
    row("critical", "levels:trend_live", "ERAA stop 580 hit (close 575)"),
    row("warning", "intents:live-fae554", "intent #3 stop ERAA: filled"),
    row("warning", "gapfade:live-fae554", "exit ticket #9 could not be filled: no bar for 2026-09-25 yet"),
    row("warning", "book:live", "held ELSA: -18 % from entry"),
    row("warning", "ara", "ELSA at ARA, locked", kind="ara", strategy="ara_sell"),
    row("info", "ticket:trend_live", "take profit: DEWI"),
    row("warning", "feed", "stockbit/feed: DOWN - last frame 900s ago"),
    row("warning", "feed", "stockbit REFRESH token expires 2026-09-30 10:00 UTC"),
    row("critical", "feed", "no session"),
])
def test_stock_actions_and_urgent_system_errors_are_pushed(r: dict) -> None:
    assert ap.actionable(r) and ap.push_now(r)


@pytest.mark.parametrize("r", [
    row("info", "signal:value_strict", "Value strict: 14 to hold", kind="signal"),
    row("info", "ml", "ML daily 2026-09-25: 12 model", kind="ml"),
    row("info", "ara", "ARA watch 2026-09-25: TRUK 25 %"),
    row("warning", "ara", "ARA watch failed (exit 1): boom"),
    row("warning", "regime", "The COMPOSITE closed under its 200-day average", kind="regime"),
    row("warning", "ticket:trend_live", "regime OFF (COMPOSITE 6242 under its 200-day average)"),
    row("info", "ticket:trend_live", "entry gate: BBRI"),
    row("warning", "gapfade:paper_gapfade", "no gap-fade scan for 2026-09-24: only 0 opening prints"),
    row("warning", "feed", "datafeed coverage under 95 % on 12 names", kind="feed"),
    row("warning", "macro", "macro pull: vix failed; the rest refreshed"),
    row("warning", "ml", "ML intraday training failed: KeyError"),
    row("warning", "crosscheck", "60 of 60 sampled codes disagree"),
    row("warning", "broker", "broker snapshot stopped: HTTP 401"),
    row("warning", "daily", "no bar for 2026-09-23 by 18:00 WIB - retrying to 20:00"),
    row("info", "book:live", "held UNTR: [affiliated_tx] Transaksi Afiliasi"),
])
def test_noise_is_neither_shown_nor_pushed(r: dict) -> None:
    assert not ap.actionable(r) and not ap.push_now(r)


def test_failed_job_is_shown_but_pushed_only_by_the_digest() -> None:
    r = row("critical", "daily", "daily 2026-09-25: IdxFetchError: HTTP 403")
    assert ap.actionable(r) and ap.deferred(r) and not ap.push_now(r)


def test_execution_reads_are_shown_never_pushed() -> None:
    r = row("info", "exec:live-fae554", "BBCA 2 lot left @ 9,050", kind="exec")
    assert ap.actionable(r) and not ap.push_now(r)


def test_tag_sets_the_flag() -> None:
    assert ap.tag(row("info", "ml", "x"))["actionable"] is False


@pytest.mark.parametrize("r", [
    row("warning", "gapfade:paper_gapfade", "exit ticket #9 could not be filled: no bar yet"),
    row("warning", "ticket:paper-edbb01", "combo ticket #12 not issued - cash"),
    row("critical", "levels:paper_trend", "ERAA stop hit"),
    row("warning", "book:live", "held SMDR: [exchange_query] 2026-09-22 Penjelasan atas Permintaan Penjelasan Bursa"),
    row("warning", "book:live", "held ACES: [auditor] change of auditor"),
    row("warning", "gapfade:live-fae554", "1 position(s) survived the previous session and were swept at today's open: TSTB"),
])
def test_paper_books_non_freeze_disclosures_and_self_handled_reports_are_quiet(r: dict) -> None:
    assert not ap.actionable(r) and not ap.push_now(r)


def test_a_trading_freeze_on_a_held_name_is_an_action() -> None:
    r = row("warning", "book:live", "held BUMI: [suspension] 2026-09-22 Penghentian Sementara Perdagangan")
    assert ap.actionable(r) and ap.push_now(r)


def test_direct_send_for_a_paper_book_is_dropped(monkeypatch) -> None:
    from blackheart_ingest.idx import notify, push
    calls: list = []
    monkeypatch.setattr(push, "configured", lambda: True)
    monkeypatch.setattr(push, "broadcast", lambda *a, **k: calls.append(k) or {"sent": 1, "devices": 1})
    monkeypatch.delenv(notify.TOKEN_ENV, raising=False)
    assert notify.send("[combo] KONFIRMASI ML X", book="paper-edbb01") is False
    assert calls == []
