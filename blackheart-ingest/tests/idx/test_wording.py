"""Blackridge spec §03: no directive words in the text users see (notifications, cards, reports, API messages)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCAN = ["notify.py", "push.py", "card.py", "trend_book.py", "api.py", "report.py", "overlay.py", "pack.py", "candidates.py", "quote.py", "ara.py"]


def test_user_facing_modules_have_no_directive_words() -> None:
    spec = importlib.util.spec_from_file_location("lint_words", ROOT / "scripts" / "lint-words.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = ROOT / "blackheart-ingest" / "src" / "blackheart_ingest" / "idx"
    hits = [h for name in SCAN if (src / name).exists() for h in mod.scan(src / name)]
    assert not hits, "\n".join(f"{f}:{i}: {w}" for f, i, w in hits)
