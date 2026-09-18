# blackheart-idx-mcp

The Blackheart IDX (IHSG) value desk as MCP tools for Claude. A thin wrapper over the ingest API (`blackheart-ingest`
`/idx/*`, local `:8001`): 38 tools — status/alerts, candidates, cards, the nightly pack and its answer, books, tickets
(+ validate), evidence, journal, watchlist, news, quotes, performance report, macro, strategies, studies, Telegram notify,
broker reconcile. No database access here; no strategy logic here.

Guardrails live server-side in blackheart-ingest (phase 1 of `docs/superpowers/plans/2026-09-17-idx-agent-desk-plan.md`):
every request carries `X-Idx-Actor: agent`, and the server refuses live issue/close/fills, book settings beyond the note,
halt/resume, and any issue that fails `ticket_validate` (weight/sector caps, liquidity, candidates only, cash, agent
turnover outside May). `guard.py` repeats the two-key and live-fill rules client-side so the refusal is immediate.

## Run

```
py -3.14 -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m idx_mcp --smoke        # calls /idx/ops, prints status + tool count
.venv/Scripts/python -m pytest -q               # 20 tests, no network
```

Claude Code picks the server up from `C:/Project/.mcp.json` (start the session in `C:/Project`); the ritual is in
`.claude/skills/idx-desk/SKILL.md`. Env: `IDX_API_URL` (default `http://127.0.0.1:8001`), `INGEST_AUTH_TOKEN`
(only when the ingest API has its token gate on).

Unattended: `scripts/idx-nightly.ps1` (Windows task "Blackheart IDX nightly", Mon–Fri 20:45 WIB) runs the skill's ritual
headless with these tools; `-Smoke` checks the plumbing, `-Register` (re)creates the task.
