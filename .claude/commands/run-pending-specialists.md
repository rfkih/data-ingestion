---
name: run-pending-specialists
description: Drain the specialist-review queue. Reads pending rows from the research orchestrator (specialist_review_request journal rows), spawns the matching specialist sub-agent (quant-skeptic / quant-portfolio-manager / quant-ml-judge) with the request payload, parses the VERDICT line from the sub-agent's return, and posts the verdict back via POST /specialist-review/complete. This is the operator-side driver for the Path C async-checkpoint contract — the researcher sub-agent cannot spawn sub-agents itself (harness strips Agent in nested contexts), so adversarial review runs here from the main session where Agent IS available. Idempotent — running this with no pending rows is a no-op.
---

You are draining the specialist-review queue on behalf of the quant-researcher. The researcher hit step 9d on a graduation candidate, wrote 1–3 `specialist_review_request` journal rows (skeptic always, portfolio always, ml-judge if ML candidate), and exited on the `SPECIALIST_REVIEW_PENDING` terminal. Your job: spawn the actual specialist sub-agents (which need Agent — only available from this main session, not from inside the researcher sub-agent), parse their verdicts, and post them back so the researcher can resume on its next fire.

## Hard rules

1. **One verdict per request row.** Each pending row has a unique `target_id`. Spawn the sub-agent named in `structured_data.specialist_name`, parse its `VERDICT:` line, POST `/specialist-review/complete` exactly once per row. Idempotency-Key your POST so a network blip after the sub-agent returns doesn't double-write.
2. **Verdict literal is binding.** Sub-agents must end their response with a `VERDICT: <literal>` line. Allowed literals:
   - `quant-skeptic`: `CONCUR | CONCERN | OVERRIDE_REJECT`
   - `quant-portfolio-manager`: `ADD | CONCERN | REJECT`
   - `quant-ml-judge`: `CONCUR | CONCERN | OVERRIDE_REJECT`
   If the literal is missing or malformed, do NOT guess — log a parse failure to `/agent-decisions/log` with `status:"parse_error"` and skip the row (operator can retry by re-running this command after fixing the sub-agent prompt).
3. **Do not edit request payloads.** Forward `structured_data.request_payload` verbatim into the sub-agent's spawn prompt. If a payload looks malformed, the bug is in the researcher's step 9d, not here.
4. **No retries on 4xx.** A 400 from `/specialist-review/complete` (e.g., `invalid_specialist_verdict`) means your parsed verdict didn't match the literal set — DO NOT retry; surface to operator. 5xx is retryable.
5. **Never bypass the researcher's gate.** This command writes verdicts; it does NOT decide whether the researcher proceeds. The researcher's next fire reads `/agent/state.recent_specialist_verdicts` and branches on `is_veto`. Don't try to "help" by skipping a veto verdict or downgrading OVERRIDE_REJECT to CONCERN — that's fraud.
6. **Curator is not adversarial.** quant-curator's verdicts (PROMOTE / HOLD /
   REJECT) describe whether the candidate lands in the admin inbox -- they
   don't affect the researcher's gate. Curator REJECT means "don't surface",
   not "researcher should pivot". Do NOT branch on is_veto for curator rows;
   the orchestrator's `VETO_VERDICTS["quant-curator"]` is an explicit empty
   frozenset (see `specialist_reviews.py`). Rules 1-5 (parsing, idempotency,
   no-bypass, no-payload-editing, no-4xx-retry) still apply to curator rows.

## Workflow

### 1. Query the queue

```bash
scripts/orch.sh GET /specialist-review/pending --pretty
```

(`scripts/orch.sh` lives at `/c/Project/blackheart-research-orchestrator/scripts/orch.sh`; call it with an absolute path if your cwd is different. Never `cd` first — the harness prompts on `cd && cmd`.)

Response shape: `{items: [{journal_id, strategy_code, content, structured_data, created_time, created_by}], count}`. Empty list → log "no pending reviews" and exit, this is the happy no-op path.

### 2. For each pending row, spawn the specialist sub-agent

Read `structured_data` from each row:
- `specialist_name` — drives the `subagent_type` for the `Agent` call
- `iteration_id`, `target_id` — used to key the verdict POST
- `motivating_hypothesis_id` — passed inline so the specialist can ground its reasoning
- `request_payload` — the artifacts (iteration_metrics, prescreen output, correlations, etc.) the specialist needs; forwarded verbatim
- `requested_by` — the researcher's agent name (informational)

Spawn the sub-agent:

```
Agent(
  subagent_type=<specialist_name>,    // "quant-skeptic" | "quant-portfolio-manager" | "quant-ml-judge"
  description=f"Audit iteration {iteration_id} for {strategy_code}",
  prompt=<see "Sub-agent prompt template" below>
)
```

The sub-agent loads its own system prompt from `.claude/agents/<name>.md`. You only provide the per-call artifacts + the verdict-format instruction.

### 3. Sub-agent prompt template

Use this exact shell (substitute the bracketed fields):

```
You have been spawned via /run-pending-specialists to audit a graduation candidate. The researcher cannot spawn you itself (harness strips Agent in nested sub-agent contexts), so you run on the operator's main session.

## Target

- target_id:      [target_id]
- iteration_id:   [iteration_id]
- strategy_code:  [strategy_code]
- motivating_hypothesis_id: [motivating_hypothesis_id or "none"]

## Request payload (verbatim from research_journal.structured_data.request_payload)

```json
[request_payload as pretty JSON]
```

## Instructions

Apply your standard lens battery from your system prompt (do NOT skip lenses). Reason as you normally would. You MAY call the orchestrator (`scripts/orch.sh GET ...`) for additional context like `/iterations/{iteration_id}`, `/portfolio/correlations`, `/ml-prescreen`, `/journal/{hypothesis_id}` — your `tools:` list permits it.

You may NOT:
- Modify any iteration_log / journal / queue rows.
- Call any state-changing POST.
- Spawn further sub-agents (harness blocks this anyway).

End your response with EXACTLY two lines, each on its own line:

```
VERDICT: <literal>
REASONING: <one short paragraph, ≤ 400 chars, the load-bearing argument for the verdict>
```

Allowed verdict literals for you:
- quant-skeptic:           CONCUR | CONCERN | OVERRIDE_REJECT
- quant-portfolio-manager: ADD | CONCERN | REJECT
- quant-ml-judge:          CONCUR | CONCERN | OVERRIDE_REJECT
- quant-curator:           PROMOTE | HOLD | REJECT

If you cannot reach a confident verdict (e.g., critical data missing), return CONCERN with a reasoning that names what's missing — do NOT block on OVERRIDE_REJECT / REJECT for "I'd want more data" alone. Vetos are for real methodology / portfolio / overfit problems.
```

### 4. Parse the sub-agent's return

The sub-agent's final message is in its return text. Find the verdict literal using this permissive regex (one line):

```
^[\s>*_`-]*VERDICT[\s:*_`-]+([A-Z_]{3,20})\b
```

This matches `VERDICT: CONCUR`, `**VERDICT:** CONCUR`, `> VERDICT — CONCUR`, etc. — minor markdown / blockquote / em-dash formatting around the keyword does not invalidate the line. Apply multiline flag. Take the first capture group as the literal candidate; uppercase it (in case the sub-agent emitted lowercase); validate against the per-specialist set above.

Same approach for `REASONING:` — relaxed regex, take the first line of capture or up to the next blank line. If missing, fall back to "no reasoning provided" — the verdict still posts, but flag in the summary report so the operator can investigate sub-agent prompt drift.

If `VERDICT:` line is absent or the literal is unrecognized:
- POST `/agent-decisions/log` with `specialist:<name>`, `endpoint:"path_c_async_spawn"`, `model_name:"sonnet"`, `status:"parse_error"`, `response_payload:{raw: <full return text>}`.
- Skip this row — do NOT POST `/specialist-review/complete`. Operator will see the parse error and decide.

### 5. POST the verdict back

**Use the `Write` tool to create the JSON body file. Do NOT use a heredoc —** the harness static parser rejects `cat > /tmp/foo <<'EOF' {...} EOF` patterns with `Contains brace with quote character (expansion obfuscation)`, which is exactly the playbook's documented trap (see `GET /agent/playbook` tooling.json_body_pattern).

Step-by-step:

1. Construct the body as a Python dict in your reasoning context:

   ```
   body = {
     "target_id":      <target_id from pending row>,
     "specialist_name":<name>,
     "iteration_id":   <iteration_id>,
     "strategy_code":  <strategy_code or null>,
     "verdict":        <parsed literal>,
     "reasoning":      <parsed reasoning>,
     "raw_response":   {"return_text": <sub-agent's full return text>},
     "motivating_request_id": <pending row's journal_id>
   }
   ```

2. Invoke `Write` with `file_path="C:\\Project\\tmp\\sr-complete-<target_id>.json"` and `content=<json.dumps(body)>` — pretty-printed JSON, one object per file. (Pick a deterministic filename so a retry overwrites the same file rather than littering tempfiles.)

3. POST via the wrapper:

   ```bash
   /c/Project/blackheart-research-orchestrator/scripts/orch.sh POST /specialist-review/complete \
     --body /c/Project/tmp/sr-complete-<target_id>.json \
     --ik "sr-complete-<target_id>"
   ```

Idempotency-Key based on `target_id` so a retried complete-post returns the same response and doesn't double-write. The orchestrator's `/specialist-review/complete` handler:
- Inserts the verdict journal row (`STRATEGY_OUTCOME` + `kind=specialist_review_verdict`)
- PARKED-s the matching pending request row (transaction-atomic)
- Writes an `agent_decisions` audit row with `endpoint:"path_c_async_spawn"`, `model_name:"sonnet"`
- Logs an activity row (`SPECIALIST_REVIEW_RECEIVED`)
- Returns `{verdict_journal_id, decision_id, is_veto, ...}`

### 6. Iterate

Process each pending row sequentially. Vetos do NOT short-circuit later rows — the researcher reads ALL verdicts on resume and decides. You always drain the full queue per invocation.

### 7. Summary report

After the loop, emit a one-screen summary to the operator:

```
Drained N pending specialist reviews:
  - skeptic    × <n_concur> CONCUR, <n_concern> CONCERN, <n_veto> OVERRIDE_REJECT
  - portfolio  × <n_add>    ADD,    <n_concern> CONCERN, <n_veto> REJECT
  - ml-judge   × <n_concur> CONCUR, <n_concern> CONCERN, <n_veto> OVERRIDE_REJECT
  - curator    × <n_promote> PROMOTE, <n_hold> HOLD, <n_reject> REJECT  (no researcher veto)

Parse errors:    <n_parse_errors>
HTTP errors:     <n_http_errors>

Next: researcher's next fire will read /agent/state.recent_specialist_verdicts
      and either resume at step 9 (no vetos) or pivot back to step 1 (any veto).
```

## Failure modes

**Sub-agent refuses to produce a VERDICT line** — Log `parse_error` to `/agent-decisions/log`, surface to operator. Likely cause: sub-agent's system prompt has drifted from the verdict literal set; check `.claude/agents/<name>.md`.

**Sub-agent times out** — Log `timeout` to `/agent-decisions/log`. Re-run this slash command to retry the pending row.

**`/specialist-review/complete` returns 400 `invalid_specialist_verdict`** — Your parser extracted a literal not in the allowed set. Fix the parsing logic; do NOT retry the same POST.

**`/specialist-review/complete` returns 5xx** — Retry up to 3× with 30s backoff. If still 5xx, surface to operator with the error envelope.

**Two operator sessions running this command concurrently** — Idempotency-Key on target_id prevents duplicate verdict rows. Worst case: both sessions spawn the same sub-agent (wasted tokens), the second `/complete` POST returns the cached response from the first. No data corruption.

## When to re-run

After the researcher hits `SPECIALIST_REVIEW_PENDING`, run this command. If the researcher writes more pending rows in a later session (e.g., second candidate), re-run. **No cron scheduling yet** — the operator triggers this manually (B1 contract, 2026-05-20). Future: a cron via the `schedule` skill can fire this on a 15–30min interval once the contract is validated through one or two end-to-end runs.
