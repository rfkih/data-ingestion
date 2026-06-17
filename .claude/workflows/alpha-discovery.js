export const meta = {
  name: 'alpha-discovery',
  description:
    'Graveyard-aware literature + quant-forum alpha discovery → pre-registered, falsifiable hypotheses for a dual-track research loop (trading|hedging). PRODUCER ONLY — it does not backtest. Web tools live here, never in the mechanical /tick loop. Pass args:{track, n_hypotheses?, graveyard?}.',
  phases: [
    { title: 'Graveyard' },
    { title: 'Source sweep' },
    { title: 'Synthesize' },
    { title: 'Adversarial gate' },
    { title: 'Formulate' },
    { title: 'Pre-register pack' },
  ],
}

// ── Inputs ────────────────────────────────────────────────────────────
const TRACK = (args && args.track) || 'trading'
if (!['trading', 'hedging'].includes(TRACK)) {
  log(`Invalid track "${TRACK}" — pass args:{track:'trading'|'hedging'}`)
  return { error: 'invalid_track', got: TRACK }
}
const N = (args && args.n_hypotheses) || 3
const GRAVEYARD_SUPPLEMENT = (args && args.graveyard) || null

// What the loop can ACTUALLY test — keeps discovery from proposing un-runnable ideas.
// Keep in sync with: orchestrator VALID_INTERVAL_NAMES, the research universe in
// quant-researcher.md hard constraint 1, and the feature_store catalog.
const DATA_SURFACE =
  'Symbols: BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT ONLY (5 names — cross-sectional ' +
  'rank/dispersion designs are STRUCTURALLY UNDERPOWERED at this breadth and have already ' +
  'died 3-for-3; propose per-asset time-series designs unless the idea works honestly with ' +
  'n=5). market_data is SPOT-sourced (Binance spot); perp-specific data available: funding ' +
  'rate, perp-spot basis + basis momentum. Other features: full price-action TA suite, ' +
  'Deribit DVOL implied-vol (btc/eth only: dvol level, zscore_30d, vol-of-vol), on-chain ' +
  'seeds. Intervals: 5m/15m/1h/4h/1d (1d depth: BTC back to 2017; others ~2024+). ' +
  'Backtest = cost-aware JVM engine (fees + slippage + turnover charged). New signal types ' +
  'usually require a JVM engine to emit them — flag engine-build cost honestly.'

const OBJECTIVE =
  TRACK === 'hedging'
    ? 'allocation / drawdown-reduction / vol-targeting / crisis-hedge methods that BEAT BUY-HOLD on ' +
      'risk-adjusted terms (lower maxDD and/or higher Sharpe) without giving up much CAGR — NOT standalone directional alpha.'
    : 'return-predictive alpha with a real economic reason to exist ' +
      '(who is on the other side of the trade, and why do they keep paying?).'

// ── D0: Graveyard — what is already dead (NEVER skip) ─────────────────
// Discovery without memory re-proposes falsified families. Pull the durable
// record from the orchestrator; degrade gracefully if it is unreachable.
phase('Graveyard')
const GRAVEYARD_SCHEMA = {
  type: 'object',
  properties: {
    dead_families: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          family: { type: 'string' },
          why_dead: { type: 'string' },
          evidence: { type: 'string' },
          structural_blocker: { type: 'string' },
        },
        required: ['family', 'why_dead'],
      },
    },
    no_edge_surfaces: { type: 'array', items: { type: 'string' } },
    promising_residue: {
      type: 'array',
      items: { type: 'string' },
      description: 'partial findings worth a conditioning retry (e.g. signal dead unconditionally but PF>1.15 in one regime bucket)',
    },
    fetch_ok: { type: 'boolean' },
  },
  required: ['dead_families', 'fetch_ok'],
}
const graveyard = await agent(
  `You are building the FALSIFICATION GRAVEYARD for a quant research loop so new ideas do ` +
    `not re-tread dead ground. Using Bash (git-bash available), call the research orchestrator ` +
    `read-only wrapper:\n` +
    `  bash C:/Project/blackheart-research-orchestrator/scripts/orch.sh GET '/journal?entry_type=HYPOTHESIS&status=FALSIFIED&limit=60'\n` +
    `  bash C:/Project/blackheart-research-orchestrator/scripts/orch.sh GET '/journal?entry_type=STRATEGY_OUTCOME&limit=60'\n` +
    `  bash C:/Project/blackheart-research-orchestrator/scripts/orch.sh GET '/journal?entry_type=ANTI_PATTERN&limit=30'\n` +
    `Distill into DEAD FAMILIES (mechanism-level, e.g. "unconditional funding-rate timing on majors", ` +
    `"cross-sectional dispersion on 5-name universe"), each with why it died and any STRUCTURAL ` +
    `blocker (universe breadth, data depth, trade frequency). Also list NO_EDGE surfaces ` +
    `(strategy×symbol×interval) and PROMISING RESIDUE — partial findings that suggest a ` +
    `conditioning retry rather than a dead end (regime-bucket PF>1.15, sign-correct-but-underpowered). ` +
    `If the orchestrator is unreachable after 2 tries, set fetch_ok=false and return what you can ` +
    `from this supplement alone.\n` +
    (GRAVEYARD_SUPPLEMENT ? `Operator-supplied supplement:\n${JSON.stringify(GRAVEYARD_SUPPLEMENT)}\n` : '') +
    `Track: ${TRACK}.`,
  { label: 'graveyard', phase: 'Graveyard', schema: GRAVEYARD_SCHEMA },
)
const DEAD = graveyard ? graveyard.dead_families : []
const RESIDUE = (graveyard && graveyard.promising_residue) || []
log(
  `Graveyard: ${DEAD.length} dead families, ${RESIDUE.length} promising residues` +
    (graveyard && !graveyard.fetch_ok ? ' (orchestrator unreachable — supplement only)' : ''),
)
const GRAVEYARD_BRIEF =
  `ALREADY-FALSIFIED FAMILIES (do NOT re-skin these):\n${JSON.stringify(DEAD)}\n` +
  `PROMISING RESIDUE (conditioning retries welcome):\n${JSON.stringify(RESIDUE)}`

// ── D1: Source sweep (parallel, WEB + one offline lens) ───────────────
phase('Source sweep')
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    candidates: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          mechanism: { type: 'string' },
          economic_rationale: { type: 'string' },
          source: { type: 'string' },
          url: { type: 'string' },
        },
        required: ['mechanism', 'economic_rationale', 'source'],
      },
    },
  },
  required: ['candidates'],
}

const SOURCES = [
  {
    key: 'academic',
    web: true,
    q: `Search arXiv q-fin, SSRN, and Google Scholar for RECENT work on: ${OBJECTIVE}`,
  },
  {
    key: 'forums',
    web: true,
    q:
      `Search practitioner quant forums (Quantitative Finance StackExchange, QuantConnect forum, ` +
      `Wilmott, Nuclear Phynance, r/algotrading, Elite Trader) for implementation-level ideas AND ` +
      `documented failure modes relevant to: ${OBJECTIVE}`,
  },
  {
    key: 'crypto-native',
    web: true,
    q:
      `Search crypto-native research (Deribit Insights, Glassnode/CryptoQuant research, Kaiko, ` +
      `Amberdata, BitMEX research blog, Paradigm/Galaxy research, ethresear.ch) for ` +
      `crypto-market-structure mechanisms relevant to: ${OBJECTIVE}. Focus on mechanisms with a ` +
      `STRUCTURAL counterparty: forced liquidation cascades, funding/basis dislocations around ` +
      `events, options dealer-flow (DVOL-readable), stablecoin-flow regimes, time-of-day/weekend ` +
      `liquidity effects, expiry/settlement calendar effects.`,
  },
  {
    key: 'conditioning',
    web: false,
    q:
      `NO web needed. Re-mine the graveyard for INTERACTION/CONDITIONING candidates: signals that ` +
      `failed UNCONDITIONALLY but have promising residue in one regime, vol-state, trend-state, or ` +
      `funding-state bucket. Propose mechanism = (dead signal) × (observable state filter computable ` +
      `from our features). One conditioning retry per family maximum — a second re-skin of the same ` +
      `family is p-hacking, not research.`,
  },
]

const sweeps = await parallel(
  SOURCES.map((s) => () =>
    agent(
      `You are a quant-research scout for the ${TRACK} track. ${s.q}\n\n` +
        `${GRAVEYARD_BRIEF}\n\n` +
        `We can only test ideas on this data surface: ${DATA_SURFACE}\n\n` +
        `Return candidate signal MECHANISMS (not full strategies), each with its economic rationale ` +
        `and a real source citation/url. HARD FILTERS: (1) nothing that re-skins a dead family ` +
        `unless it is an explicitly-flagged conditioning retry of promising residue; (2) no ` +
        `cross-sectional design needing more than 5 names; (3) prefer mechanisms ORTHOGONAL to ` +
        `plain price-action (funding/basis/carry/implied-vol/flow/event/calendar) — price-action ` +
        `re-skins get rejected as near-substitutes downstream.` +
        (s.web ? ` Use WebSearch/WebFetch.` : ''),
      { label: `scout:${s.key}`, phase: 'Source sweep', schema: FINDINGS_SCHEMA },
    ),
  ),
)
const allCandidates = sweeps.filter(Boolean).flatMap((r) => r.candidates)
log(`Gathered ${allCandidates.length} raw candidate mechanisms`)
if (!allCandidates.length) {
  return { track: TRACK, generated_count: 0, hypotheses: [], note: 'no candidates surfaced' }
}

// ── D2: Synthesize + dedup + testability filter ───────────────────────
phase('Synthesize')
const MECH_SCHEMA = {
  type: 'object',
  properties: {
    mechanisms: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          mechanism: { type: 'string' },
          economic_rationale: { type: 'string' },
          data_needed: { type: 'string' },
          testable: { type: 'boolean' },
          orthogonality: { type: 'string' },
          graveyard_distance: {
            type: 'string',
            description: 'one line: why this is NOT a re-skin of a dead family (or which residue it is a flagged conditioning retry of)',
          },
          sources: { type: 'array', items: { type: 'string' } },
        },
        required: ['name', 'mechanism', 'testable', 'graveyard_distance'],
      },
    },
  },
  required: ['mechanisms'],
}
const synth = await agent(
  `Collapse these ${allCandidates.length} candidate mechanisms into DISTINCT ones; drop near-duplicates. ` +
    `Mark testable=true ONLY if it is testable on: ${DATA_SURFACE}\n\n` +
    `${GRAVEYARD_BRIEF}\n\n` +
    `For each mechanism, state graveyard_distance: why it is NOT a re-skin of a dead family. ` +
    `Drop (testable=false) anything that needs >5 symbols cross-sectionally, unplumbed data, or ` +
    `re-treads a dead family without new conditioning. Rank the strongest, most ` +
    `orthogonal-to-price-action first.\n\n${JSON.stringify(allCandidates)}`,
  { phase: 'Synthesize', schema: MECH_SCHEMA },
)
const testable = synth.mechanisms.filter((m) => m.testable)
log(`${testable.length} distinct testable mechanisms (of ${synth.mechanisms.length})`)

// ── D3: Formulate (parameter-light, falsifiable, signed) then adversarial gate ─
// pipeline: each mechanism is formulated then immediately attacked — no barrier.
phase('Formulate')
const HYP_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    mechanism: { type: 'string' },
    economic_rationale: { type: 'string' },
    signal_definition: { type: 'string' },
    predicted_sign: {
      type: 'string',
      enum: ['long_when_high', 'long_when_low', 'spread', 'other'],
    },
    params: { type: 'array', items: { type: 'string' } },
    instrument: { type: 'string' },
    interval: { type: 'string' },
    declared_n_trials: { type: 'integer' },
    engine_exists: {
      type: 'boolean',
      description: 'true if an existing JVM engine can emit this signal via params; false if a new engine must be built first',
    },
    engine_note: { type: 'string' },
    sources: { type: 'array', items: { type: 'string' } },
  },
  required: ['title', 'signal_definition', 'predicted_sign', 'declared_n_trials', 'instrument', 'interval', 'engine_exists'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    survives: { type: 'boolean' },
    predicted_failure_mode: { type: 'string' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    fix: { type: 'string', description: 'if fixable, the one change that would make it survive' },
  },
  required: ['survives', 'predicted_failure_mode', 'confidence'],
}

const candidatePool = testable.slice(0, Math.max(N + 2, 5)) // overshoot — the gate will kill some
const gated = await pipeline(
  candidatePool,
  (m) =>
    agent(
      `Turn this mechanism into a PARAMETER-LIGHT, FALSIFIABLE signal for the ${TRACK} track.\n` +
        `State: (1) the exact signal_definition as an equation/rule over our features; ` +
        `(2) the PREDICTED SIGN/direction; (3) a MINIMAL motivated param set (a few combos, NOT a grid); ` +
        `(4) the instrument + interval to test (think about TRADE FREQUENCY: the stat gate needs ` +
        `n>=100 trades — a signal firing 6 times in 2.5 years can never validate; pick the interval ` +
        `where the mechanism plausibly fires often enough); (5) a DECLARED n_trials = the count of ` +
        `every param combo you would examine (this feeds DSR multiplicity — under-count is fraud); ` +
        `(6) engine_exists: can an EXISTING JVM engine emit this via params/sentinels, or does it ` +
        `need a new engine build (be honest — engine builds cost operator days).\n` +
        `Mechanism:\n${JSON.stringify(m)}\nData surface: ${DATA_SURFACE}`,
      { label: `formulate:${m.name}`, phase: 'Formulate', schema: HYP_SCHEMA },
    ),
  (h, m) =>
    h == null
      ? null
      : agent(
          `Adversarial gate (phase: kill before capital is spent). Try to REFUTE this pre-registration ` +
            `candidate for the ${TRACK} track. Attack on: (a) is it a near-substitute of a dead ` +
            `graveyard family; (b) can it actually reach n>=100 trades on the proposed ` +
            `instrument/interval given its firing condition; (c) does the data surface really carry ` +
            `the inputs (${DATA_SURFACE}); (d) does the economic rationale survive costs (taker fees ` +
            `+ slippage charged per trade); (e) is the predicted sign actually pinned down by the ` +
            `mechanism or could either sign be rationalized post-hoc.\n\n${GRAVEYARD_BRIEF}\n\n` +
            `Candidate:\n${JSON.stringify(h)}\n\nDefault to survives=false when uncertain.`,
          { label: `gate:${m.name}`, phase: 'Adversarial gate', schema: VERDICT_SCHEMA },
        ).then((v) => ({ hypothesis: h, verdict: v })),
)
const survivors = gated
  .filter(Boolean)
  .filter((g) => g.verdict && g.verdict.survives)
  .map((g) => ({ ...g.hypothesis, track: TRACK }))
const killed = gated
  .filter(Boolean)
  .filter((g) => g.verdict && !g.verdict.survives)
  .map((g) => ({ title: g.hypothesis.title, predicted_failure_mode: g.verdict.predicted_failure_mode, fix: g.verdict.fix || null }))
log(`Adversarial gate: ${survivors.length} survive, ${killed.length} killed pre-registration`)

const preregistered = survivors.slice(0, N)

// ── D4: Pre-register pack (producer only) ─────────────────────────────
phase('Pre-register pack')
log(`Produced ${preregistered.length} pre-registered hypotheses for track=${TRACK}`)
return {
  track: TRACK,
  generated_count: preregistered.length,
  hypotheses: preregistered,
  killed_at_gate: killed,
  graveyard_families_considered: DEAD.length,
  handoff:
    'CONFIRMATORY DISCIPLINE — for EACH hypothesis, BEFORE any backtest: ' +
    '(1) POST /journal {entry_type:"HYPOTHESIS", status:"ACTIVE", title, content:<rationale>, ' +
    'structured_data:{track, mechanism, signal_definition, predicted_sign, declared_n_trials, sources}} ' +
    'to PRE-REGISTER; capture the journal_id. ' +
    '(2) If engine_exists=false, do NOT queue — journal a DATA_WISHLIST naming the engine build and ' +
    'hand to the operator; queueing an untestable hypothesis burns a review round. ' +
    '(3) For a NEW surface (strategy×symbol×interval with no prior iterations), run the cheap ' +
    'POST /null-screen gate (playbook §2.8) BEFORE committing the full sweep. ' +
    '(4) THEN POST /queue {track, instrument, interval_name:interval, ' +
    'sweep_config:{...combos, track, n_trials:declared_n_trials}, hypothesis:<journal_id>}. ' +
    'The HYPOTHESIS row MUST exist before /queue (confirmatory, not scan-then-formalize). ' +
    'Do NOT exceed declared_n_trials — every extra combo raises the DSR bar. ' +
    'Web tools were used ONLY in this discovery workflow; the /tick loop never touches the web.',
}
