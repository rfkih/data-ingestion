---
name: memory
description: Search and write the agent's long-term memory through the `mem` index (SQLite full-text + entity + link graph over ~/.claude/projects/*/memory). Use BEFORE claiming anything about past work — a study's result, why something was or was not built, an old number — and BEFORE writing a new memory. Also for "what do we know about study 153 / menu 34 / book live-fae554", duplicate checks, stale-memory sweeps, and republishing MEMORY.md.
---

# Memory: search before you claim, check before you write

The markdown files under `~/.claude/projects/<scope>/memory/` are the source of truth. `mem` is a disposable SQLite
index over **every scope at once** (485+ memories), reachable three ways: full text (FTS5 BM25), exact entities
(`study 153`, `menu 34`, `book live-fae554`, `migration 0041`, file paths) and the `[[wikilink]]` graph.

    PY=C:/Project/blackheart-ingest/.venv/Scripts/python.exe        # any python works, stdlib only
    MEM=C:/Users/rifki/.claude/tools/mem.py

## The two habits

**1. Before a factual claim about past work, look it up.** The auto-loaded `MEMORY.md` carries titles only; the facts
live in the files.

    $PY $MEM find "loser filter value book"      # ranked snippets, with the file path
    $PY $MEM why study 153                       # every memory tied to one entity, with the matching lines
    $PY $MEM get project_ml_batch_2026-09-25     # one memory, whole

This exists because of a real failure: on 2026-09-25 the claim "the 250d loser filter is unwired money" went to the
operator and had to be retracted — `why study 153` returns the memory saying it had already been tested on the value
book and lost. Cost: 0.002 ms. Not doing it cost a correction in front of the operator.

**2. Before writing a memory, check for a duplicate, then write through the tool.**

    $PY $MEM check "cash floor drawdown combo book"                 # exit 2 = something already covers this
    $PY $MEM new --scope blackheart-equity --type feedback \
        --name feedback_some_rule --hook "one line, this becomes the index entry" --body-file -   # body on stdin
    $PY $MEM update <name> --append-file - | --verified | --supersede <old-name>

`new` refuses when something similar exists (override with `--force` only when you mean a genuinely separate fact), fills
the frontmatter, extracts entities and links, and republishes the index. **A fact that contradicts an older memory is
written with `--supersedes <old>`**, never as a second note: the old one drops to `superseded` (still findable, ranked
down) instead of two contradictory memories living side by side.

## Housekeeping

    $PY $MEM reindex          # after editing memory files by hand (incremental, ~3 s full)
    $PY $MEM publish --apply  # regenerate MEMORY.md: one short line per memory, capped
    $PY $MEM doctor           # oversized index lines, orphan links, superseded chains, name collisions
    $PY $MEM stale --days 90  # memories naming code files that have not been verified since
    $PY $MEM brief            # the few lines a new session needs

`publish --migrate --apply` is the repair for a `MEMORY.md` that has grown content inside its index lines: the long hook
is appended to its own memory file first (lossless, old index backed up under `.index/`), then a short line is published.
It cut this project's index from 21,869 to ~5,800 bytes with nothing lost.

## How ranking works, so you can read the output

`0.45 × text (scaled by how many query terms the memory actually contains) + 0.20 × recency (half-life by type: feedback
730 d, project 240 d) + 0.15 × how often it has been recalled + 0.10 × type prior + 0.10 × link proximity`, times a status
multiplier (`superseded` 0.35, `archived` 0.2). A `*` marks a memory reached by an exact entity hit rather than text.
Queries that find nothing land in `.index/misses.log` — that log, not corpus size, is the evidence that would justify
adding embeddings later.

Design notes: the artifact "Arsitektur Memori Blackheart"; the tool's own memory is `reference_mem_tool`.
