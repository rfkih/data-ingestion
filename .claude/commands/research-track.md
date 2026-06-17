---
description: Launch one quant-researcher loop scoped to a research track (trading|hedging)
argument-hint: <trading|hedging>
---

You are launching ONE track of the dual-track research system. The track is: **$ARGUMENTS**.

Spec: `blackheart-research-orchestrator/docs/specs/2026-06-06-dual-track-research-design.md` (Components 1, 3, 4).
Each track runs in its OWN CLI session; run this command once per CLI so two loops run in parallel without poisoning each other's state.

## Step 1 — Validate the track
`$ARGUMENTS` MUST be exactly `trading` or `hedging`. If it is anything else (or empty), STOP and tell the operator the valid values. Do not guess.

## Step 2 — Resolve track config
- `trading` → agent_name=`quant-researcher-trading`, track=`trading`, gate=V60 (≥10%/yr ROBUST standalone).
- `hedging` → agent_name=`quant-researcher-hedging`, track=`hedging`, gate=`beats_buy_hold_risk_adj` (Phase 2 — until that lands, the hedging loop runs on the V60 thresholds; it is still safe to run).

## Step 3 — Confirm the target DB (prod vs local)
The LOCAL orchestrator (:8082) runs against an EMPTY dev DB (see memory `project_prod_research_from_local_tunnel`). Before booting:
- Determine whether :8082 is tunneled to prod or is local dev.
- If it is local dev, WARN the operator and require explicit confirmation before continuing — two loops on an empty dev DB produce nothing.

## Step 4 — Boot the scoped researcher
Spawn the `quant-researcher` sub-agent (the `Agent` tool is available because this is a top-level CLI session). In its instructions, require:
- `X-Agent-Name: <agent_name from Step 2>` on every orchestrator call.
- Every `GET /agent/state` call includes `?track=<track>`.
- Every `POST /queue`, `/tick`, `/tick/drain` includes `track: "<track>"` in the body.
- Every journal write (HYPOTHESIS, RUN_SUMMARY, NULL_SCREEN_RESULT, SESSION_CHECKPOINT, specialist requests) stamps `structured_data.track = "<track>"`.

These are wired and tested in the orchestrator (Phase 1): the digest, queue claim, queue-counts, and the re-discovery gate are all track-scoped; an untagged/global discard still blocks every track. The `track=hedging` economic gate is the equity-level **beats-buy-hold** gate (Phase 2a, stashed on `metrics_snapshot.hedging_gate`), not V11/V60.

## Step 4b — Get a fresh hypothesis (theory-first)
When the loop needs a new hypothesis line, prefer the **alpha-discovery** workflow over re-tuning a tapped axis:
`Workflow(name="alpha-discovery", args={ track: "<track>", n_hypotheses: 3 })` → returns pre-registered, falsifiable hypotheses sourced from papers + quant forums. The workflow is **graveyard-aware** (phase 0 pulls FALSIFIED hypotheses + ANTI_PATTERN rows from the orchestrator itself) and runs an adversarial pre-registration gate, so its output is already filtered against dead families, 5-name XS designs, and n<100 trade-frequency traps. Each hypothesis carries `engine_exists` — if false, hand the engine build to the operator instead of queueing. Then follow its `handoff`: **pre-register** each via `POST /journal` (HYPOTHESIS + `structured_data.track`) BEFORE enqueuing via `POST /queue` (with the declared `n_trials`). Confirmatory only — never scan-then-formalize; never exceed `declared_n_trials`. Web tools live in discovery; the `/tick` loop never touches the web.

## Step 5 — Checkpoint-to-operator contract
The researcher runs autonomously BETWEEN decision points. At each of these three decision points it MUST:
1. Write a track-tagged `SESSION_CHECKPOINT` journal row (entry_type=RUN_SUMMARY, title prefix `SESSION_CHECKPOINT_<TRACK>`, `structured_data.track` set, plus a `checkpoint_kind` of `graduation_candidate` | `pivot` | `archetype_exhaustion`).
2. RETURN to this CLI session with a compact summary of the decision and its recommendation.
3. WAIT — do not auto-decide. The operator answers; this session resumes the sub-agent (SendMessage) with the decision.

Decision points: (a) a graduation candidate is ready, (b) a pivot decision (axis/archetype exhausted), (c) an archetype-exhaustion terminal.

## Hard rules (unchanged)
- Research-only: never promote to live, never deploy. V11/V60 are frozen — do not loosen to fit a candidate.
- Do not call the Trading JVM (:8080). Drive the loop through the orchestrator (:8082).
