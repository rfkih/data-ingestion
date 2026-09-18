#!/usr/bin/env python3
"""Word-blacklist lint for user-facing text (Blackridge spec §03: tool, not advice).

Fails when a directive word appears in a scanned file: words that turn a screener/score/signal into a recommendation.
Sides of the user's own ticket lines ("buy"/"sell" as data) are not directive; those screens are allow-listed by path.
A line ending in ``wording-ok`` (in a comment) is skipped — use it only for the operator-only surfaces.

  python scripts/lint-words.py PATH [PATH ...]      (directories are walked; .py .ts .tsx .md .json)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORDS = [
    # Indonesian
    r"rekomendasi", r"direkomendasikan", r"saham pilihan", r"pilihan kami", r"top picks?", r"target harga", r"harga wajar kami",
    r"potensi naik", r"probabilitas naik", r"akurasi sinyal", r"jangan lewatkan", r"peluang emas", r"dijamin", r"pasti (untung|naik)",
    r"beli sekarang", r"jual sekarang", r"sinyal beli", r"sinyal jual", r"waktunya beli", r"waktunya jual",
    # English
    r"recommend(?:ed|ation|ations|s)?", r"strong (?:buy|sell)", r"buy now", r"sell now", r"buy signal", r"sell signal",
    r"target price", r"price target", r"don'?t miss", r"guaranteed", r"win rate", r"signal accuracy", r"probability of (?:a )?(?:rise|gain|doubling)",
]
PATTERN = re.compile(r"(?<![\w-])(?:" + "|".join(WORDS) + r")(?![\w-])", re.IGNORECASE)
EXTS = {".py", ".ts", ".tsx", ".md", ".json"}
ALLOW_DIRS = ("/ticket/", "/fill/", "/journal/", "/m/ticket", "/m/fill", "/m/journal", "/tests/", "/research/", "/docs/", "/node_modules/", "/.next/")
ALLOW_FILES = {"ticket.py", "journal.py", "consensus.py",                  # third-party analyst fields, not our copy
               "lint-words.py", "lint-words.mjs", "wording.test.ts", "test_wording.py"}
ESCAPE = "wording-ok"


def scan(path: Path) -> list[tuple[Path, int, str]]:
    hits = []
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.suffix in EXTS]
    for f in files:
        s = f.as_posix()
        if f.name in ALLOW_FILES or any(a in s for a in ALLOW_DIRS):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if ESCAPE in line:
                continue
            m = PATTERN.search(line)
            if m:
                hits.append((f, i, m.group(0)))
    return hits


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    hits = [h for a in argv for h in scan(Path(a))]
    for f, i, w in hits:
        print(f"{f.as_posix()}:{i}: directive word {w!r}")
    print(f"lint-words: {len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
