"""logos: saves PNGs, remembers misses, treats one 403 as a missing logo and a run of them as the CDN refusing."""
from __future__ import annotations

from blackheart_ingest.idx import logos

PNG = b"\x89PNG\r\n\x1a\nxx"


def test_fetch_saves_skips_and_remembers_misses(tmp_path, monkeypatch):
    monkeypatch.setattr(logos, "logo_dir", lambda: tmp_path)
    answers = {"BBCA": (200, PNG), "NOPE": (403, b""), "HTML": (200, b"<html>")}
    get = lambda url: answers[url.rsplit("/", 1)[1][:-4]]  # noqa: E731
    r = logos.fetch(["BBCA", "NOPE", "HTML"], getter=get, sleep=lambda s: None)
    assert r["saved"] == 1 and sorted(r["missing"]) == ["HTML", "NOPE"] and r["stopped"] is None
    assert (tmp_path / "BBCA.png").read_bytes() == PNG and (tmp_path / "NOPE.missing").exists()
    again = logos.fetch(["BBCA", "NOPE"], getter=lambda u: (_ for _ in ()).throw(AssertionError("asked again")), sleep=lambda s: None)
    assert again["have"] == 2 and again["asked"] == 0
    monkeypatch.setattr(logos, "logo_dir", lambda: tmp_path)
    assert logos.path_for("bbca") == tmp_path / "BBCA.png" and logos.path_for("NOPE") is None and logos.path_for("../x") is None


def test_a_run_of_403s_stops_and_forgets_the_false_misses(tmp_path, monkeypatch):
    monkeypatch.setattr(logos, "logo_dir", lambda: tmp_path)
    codes = [f"C{i}" for i in range(10)]
    r = logos.fetch(codes, getter=lambda u: (403, b""), sleep=lambda s: None)
    assert r["stopped"] and r["asked"] == logos.MAX_DENIED
    assert not list(tmp_path.glob("*.missing"))                            # asked again on the next run
