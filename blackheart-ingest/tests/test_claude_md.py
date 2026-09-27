"""Token budget guard (phase 1, 2026-09-28): CLAUDE.md is loaded into every AI session that touches this repo, so it stays a
map - purpose, commands, always-on hazards, module map, and a table of the docs/agent-context topic files - and the detail
lives in those files. It had grown to 73 KB (~18k tokens a session) as a changelog before the split."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 20_000


def _map() -> str:
    return (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_claude_md_stays_a_map() -> None:
    size = (ROOT / "CLAUDE.md").stat().st_size
    assert size <= MAX_BYTES, f"CLAUDE.md is {size:,} B (cap {MAX_BYTES:,}): move the detail into docs/agent-context/*.md"


def test_every_topic_file_the_map_names_exists_and_every_topic_file_is_named() -> None:
    text = _map()
    named = set(re.findall(r"docs/agent-context/([A-Za-z0-9_.-]+\.md)", text))
    on_disk = {p.name for p in (ROOT / "docs" / "agent-context").glob("*.md")}
    assert named, "CLAUDE.md must route to its topic files"
    assert not named - on_disk, f"CLAUDE.md points at missing files: {sorted(named - on_disk)}"
    assert not on_disk - named, f"topic files the map never mentions: {sorted(on_disk - named)}"
