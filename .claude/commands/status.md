---
description: One-screen desk status — live books, active strategies, system health, chain, feed
allowed-tools: Bash(python scripts/status.py:*)
---

Run `python scripts/status.py $ARGUMENTS` from `C:/Project` and report what it says.

Blocks: `health` `chain` `books` `strategies` `tickets` `feed` — pass one or more to narrow it,
or nothing for all of them. `--json` for the same facts as JSON.

Do **not** curl the worker, query Postgres or read source to answer this. The script is the
answer; read its output and summarise. Only dig further if the script itself reports a failure
and the user asks why.
