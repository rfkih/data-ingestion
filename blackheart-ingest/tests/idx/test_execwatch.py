"""Execution-timing read (menu 28b / study #99): the pure lean/act logic that turns a book imbalance into where to place
an already-decided line, and the note it shows. No database — the read() path is exercised by the API test with a feed."""
from __future__ import annotations

import pytest

from blackheart_ingest.idx import execwatch as ew


def test_lean_buy_takes_the_offer_only_when_the_book_leans_up() -> None:
    # book leaning up (bid-heavy, microprice above mid): a buyer takes the offer now, it is about to cost more
    assert ew.lean("buy", 0.5, 0.4) == "offer" and ew.acts_now("buy", "offer") is True
    # leaning down: a buyer rests at the bid, the price is coming to them
    assert ew.lean("buy", -0.5, -0.4) == "bid" and ew.acts_now("buy", "bid") is False
    # imbalance without the microprice confirming, or below the threshold: no edge
    assert ew.lean("buy", 0.5, -0.1) == "balanced"
    assert ew.lean("buy", 0.2, 0.4) == "balanced"
    assert ew.lean("buy", None, None) == "unknown"


def test_lean_sell_mirrors_the_buy_side() -> None:
    # leaning down: a seller takes the bid now, it is dropping
    assert ew.lean("sell", -0.5, -0.4) == "bid" and ew.acts_now("sell", "bid") is True
    # leaning up: a seller rests at the offer, the price is coming up to them
    assert ew.lean("sell", 0.5, 0.4) == "offer" and ew.acts_now("sell", "offer") is False
    assert ew.lean("sell", 0.0, 0.0) == "balanced"


def test_note_is_factual_and_free_of_directive_words() -> None:
    import importlib.util
    from pathlib import Path

    # From THIS file, like test_ara.py and test_wording.py do - not from the package. `ew.__file__`
    # points into site-packages once the wheel is installed, and parents[4] there is the interpreter's
    # lib directory, so CI failed on a missing scripts/lint-words.py while every local run passed.
    root = Path(__file__).resolve().parents[3]
    linter = root / "scripts" / "lint-words.py"
    if not linter.exists():
        pytest.skip(f"no word linter at {linter}")
    spec = importlib.util.spec_from_file_location("lint_words", linter)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    notes = [
        ew._note("buy", "offer", 0.5),
        ew._note("buy", "bid", -0.5),
        ew._note("sell", "bid", -0.5),
        ew._note("sell", "offer", 0.5),
        ew._note("buy", "balanced", 0.0),
        ew._note("buy", "unknown", None),
    ]
    assert ew._note("buy", "offer", 0.5) == "Book leaning up — take the offer"
    assert ew._note("buy", "bid", -0.5) == "Book leaning down — rest at the bid"
    for n in notes:
        assert not mod.PATTERN.search(n), n
