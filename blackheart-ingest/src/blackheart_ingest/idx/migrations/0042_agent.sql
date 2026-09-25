-- 0042  the online learning agent (operator, 2026-09-25: "kalau untung dapet reward, kita kasih modal" -> an agent that
--       trades a virtual Rp 20 M book on the live tick feed and learns from every new session). idx/agent.py.
--
--   agent_sample    the counterfactual record the agent learns from: for every name the feed carries, at every decision
--                   minute of a settled session, what each action (TP1 / TP2 bracket) would have earned from the tape. Full
--                   feedback - the tape tells what any action would have paid, not only the one taken.
--   agent_decision  what an agent actually chose at a decision minute (agent 'ts' = Thompson sampling, 'random' = the placebo
--                   with the same number of picks), and, once settled, the paper fill, exit and P&L.
--   agent_model     each nightly refit: per-action Bayesian linear posterior + the feature scaler, as JSON.
CREATE TABLE IF NOT EXISTS idx.agent_sample (
    d           DATE NOT NULL,
    minute      TIMESTAMPTZ NOT NULL,
    code        TEXT NOT NULL,
    action      TEXT NOT NULL,
    feats       JSONB NOT NULL,
    entry_px    DOUBLE PRECISION NOT NULL,
    exit_px     DOUBLE PRECISION NOT NULL,
    exit_reason TEXT NOT NULL,
    reward      DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (d, minute, code, action)
);

CREATE TABLE IF NOT EXISTS idx.agent_decision (
    id          BIGSERIAL PRIMARY KEY,
    agent       TEXT NOT NULL,
    d           DATE NOT NULL,
    minute      TIMESTAMPTZ NOT NULL,
    code        TEXT NOT NULL,
    action      TEXT NOT NULL,
    score       DOUBLE PRECISION,
    model_id    BIGINT,
    feats       JSONB,
    decided_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    lots        INTEGER,
    entry_px    DOUBLE PRECISION,
    exit_px     DOUBLE PRECISION,
    exit_reason TEXT,
    reward      DOUBLE PRECISION,
    pnl         NUMERIC(20, 2),
    settled_at  TIMESTAMPTZ,
    UNIQUE (agent, d, minute, code)
);
CREATE INDEX IF NOT EXISTS agent_decision_d_idx ON idx.agent_decision (d);

CREATE TABLE IF NOT EXISTS idx.agent_model (
    id          BIGSERIAL PRIMARY KEY,
    fitted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_to     DATE NOT NULL,
    n           INTEGER NOT NULL,
    params      JSONB NOT NULL
);
