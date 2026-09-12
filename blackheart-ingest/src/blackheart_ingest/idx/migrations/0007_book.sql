-- Position book: the operator's real holdings ('live', entered by hand from broker fills) and the paper track ('paper',
-- hypothetical fills at the next open). Positions are derived from fills; marks and NAV are derived daily.
CREATE TABLE idx.book (
    book          TEXT PRIMARY KEY,                       -- live | paper | <test names>
    cash          NUMERIC(20,2) NOT NULL DEFAULT 0,
    fee_buy_pct   NUMERIC(6,4) NOT NULL DEFAULT 0.15,     -- percent of gross, applied when a fill carries no fee
    fee_sell_pct  NUMERIC(6,4) NOT NULL DEFAULT 0.25,
    div_tax_pct   NUMERIC(6,4) NOT NULL DEFAULT 10,       -- final tax on dividends for individuals
    broker        TEXT,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO idx.book (book, note) VALUES ('live', 'operator''s real positions, entered by hand'),
                                        ('paper', 'paper track of the annual value book');

CREATE TABLE idx.fill (
    id          BIGSERIAL PRIMARY KEY,
    book        TEXT NOT NULL REFERENCES idx.book (book),
    trade_date  DATE NOT NULL,
    code        TEXT NOT NULL,
    side        TEXT NOT NULL,                            -- buy | sell | split (lot adjustment from a corporate action)
    lots        NUMERIC(14,2) NOT NULL,                   -- IDX round lot = 100 shares; split rows carry the NEW lot count
    price       NUMERIC(18,4) NOT NULL,                   -- per share; split rows carry the NEW average price
    fee         NUMERIC(18,2) NOT NULL DEFAULT 0,         -- absolute, in IDR
    source      TEXT NOT NULL DEFAULT 'manual',           -- manual | paper | import | corporate_action
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX fill_book_date ON idx.fill (book, trade_date, code);

CREATE TABLE idx.position (
    book          TEXT NOT NULL REFERENCES idx.book (book),
    code          TEXT NOT NULL,
    lots          NUMERIC(14,2) NOT NULL,
    avg_price     NUMERIC(18,4) NOT NULL,                 -- average cost per share, fees included
    cost_basis    NUMERIC(20,2) NOT NULL,
    realized_pnl  NUMERIC(20,2) NOT NULL DEFAULT 0,       -- cumulative, closed lots only
    dividends     NUMERIC(20,2) NOT NULL DEFAULT 0,       -- cumulative net cash dividends credited
    opened_at     DATE,
    last_fill_at  DATE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (book, code)
);

CREATE TABLE idx.book_mark (
    book        TEXT NOT NULL REFERENCES idx.book (book),
    trade_date  DATE NOT NULL,
    code        TEXT NOT NULL,
    lots        NUMERIC(14,2) NOT NULL,
    close       NUMERIC(18,4),
    value       NUMERIC(20,2),
    cost_basis  NUMERIC(20,2),
    unrealized  NUMERIC(20,2),
    PRIMARY KEY (book, trade_date, code)
);

CREATE TABLE idx.book_nav (
    book          TEXT NOT NULL REFERENCES idx.book (book),
    trade_date    DATE NOT NULL,
    cash          NUMERIC(20,2) NOT NULL,
    positions     NUMERIC(20,2) NOT NULL,
    nav           NUMERIC(20,2) NOT NULL,
    n_positions   INTEGER NOT NULL,
    dividends     NUMERIC(20,2) NOT NULL DEFAULT 0,       -- credited on this date (net)
    PRIMARY KEY (book, trade_date)
);

-- alerts about held names are deduplicated on (job, message) while unacknowledged
CREATE INDEX alert_open_message ON idx.alert (job, message) WHERE acknowledged_at IS NULL;
