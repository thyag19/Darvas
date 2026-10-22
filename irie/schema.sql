-- irie schema (milestone M1). Portable SQL: validated by executing it on SQLite in the test-suite;
-- it uses only constructs Postgres also accepts (TEXT/NUMERIC/DATE/INTEGER, CHECK, FK) but has NOT been
-- run on PostgreSQL yet. In Postgres, prefer NUMERIC(18,8) for amounts and TIMESTAMPTZ for *_at columns.
--
-- Principles
--   * a missing value is NULL, never 0; unavailable amounts are rows with NULL amount and include = 0
--   * every observation names its source; every source carries a grade and a display-licence flag
--   * nothing is overwritten: corrections are new rows linked to an import run

CREATE TABLE source (
    source_id        TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    grade            TEXT NOT NULL CHECK (grade IN ('EXCHANGE','ISSUER','REGULATOR','AGGREGATOR','UNKNOWN')),
    url              TEXT NOT NULL DEFAULT '',
    display_cleared  INTEGER NOT NULL DEFAULT 0 CHECK (display_cleared IN (0,1)),  -- licence gate; default NOT cleared
    licence_note     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE source_document (
    document_id   TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES source(source_id),
    url           TEXT NOT NULL DEFAULT '',
    retrieved_at  TEXT,            -- UTC ISO-8601, e.g. 2026-10-22T10:15:00Z
    sha256        TEXT,
    note          TEXT NOT NULL DEFAULT ''
);

CREATE TABLE instrument (
    instrument_key  TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('REIT','INVIT','ETF')),
    etf_category    TEXT CHECK (etf_category IN ('EQUITY_BROAD','EQUITY_SECTOR_THEMATIC_FACTOR','GOLD_SILVER','DEBT','INTERNATIONAL','OTHER')),
    distributes     INTEGER CHECK (distributes IN (0,1)),   -- ETF payout policy; NULL = unknown
    isin            TEXT UNIQUE,
    CHECK (type = 'ETF' OR etf_category IS NULL)
);

CREATE TABLE listing (
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    exchange        TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    scrip_code      TEXT,
    PRIMARY KEY (exchange, symbol)
);

CREATE TABLE price_eod (
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    trade_date      DATE NOT NULL,
    venue           TEXT NOT NULL DEFAULT '',
    close           NUMERIC NOT NULL CHECK (close > 0),
    source_id       TEXT NOT NULL REFERENCES source(source_id),
    retrieved_at    TEXT,            -- UTC ISO-8601: when WE fetched it (trade_date = when the market observed it, IST date)
    document_id     TEXT REFERENCES source_document(document_id),
    PRIMARY KEY (instrument_key, trade_date, venue, source_id)
);

CREATE TABLE nav (
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    nav_date        DATE NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('FAIR_VALUE','BOOK','FUND_NAV')),
    nav             NUMERIC NOT NULL CHECK (nav > 0),
    grade           TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (grade IN ('EXCHANGE','ISSUER','REGULATOR','AGGREGATOR','UNKNOWN')),
    source_id       TEXT NOT NULL REFERENCES source(source_id),
    document_id     TEXT REFERENCES source_document(document_id),
    retrieved_at    TEXT,
    PRIMARY KEY (instrument_key, nav_date, kind, source_id)
);

CREATE TABLE leverage (
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    as_of_date      DATE NOT NULL,
    definition      TEXT NOT NULL CHECK (definition IN ('SEBI_NET_BORROWINGS_RATIO','NET_DEBT_TO_GAV','NET_DEBT_TO_EV','DEBT_TO_EV','NET_DEBT_TO_AUM','OTHER')),
    value           NUMERIC NOT NULL,
    definition_note TEXT NOT NULL DEFAULT '',
    grade           TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (grade IN ('EXCHANGE','ISSUER','REGULATOR','AGGREGATOR','UNKNOWN')),
    source_id       TEXT NOT NULL REFERENCES source(source_id),
    retrieved_at    TEXT,
    PRIMARY KEY (instrument_key, as_of_date, definition, source_id)
);

CREATE TABLE unit_count (
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    as_of_date      DATE NOT NULL,
    units           NUMERIC NOT NULL CHECK (units > 0),
    source_id       TEXT REFERENCES source(source_id),
    PRIMARY KEY (instrument_key, as_of_date)
);

CREATE TABLE import_run (
    run_id        TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    file_sha256   TEXT NOT NULL,
    imported_at   TEXT NOT NULL,     -- UTC ISO-8601; supplied by the caller, never read from a clock inside the engine
    rows_read     INTEGER NOT NULL,
    accepted      INTEGER NOT NULL,
    rejected      INTEGER NOT NULL
);

CREATE TABLE import_issue (
    run_id    TEXT NOT NULL REFERENCES import_run(run_id),
    row_number INTEGER NOT NULL,
    severity  TEXT NOT NULL CHECK (severity IN ('REJECT','REVIEW','INFO')),
    code      TEXT NOT NULL,
    message   TEXT NOT NULL,
    raw_json  TEXT
);

CREATE TABLE distribution_event (
    event_id        TEXT PRIMARY KEY,
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    ex_date         DATE NOT NULL,
    record_date     DATE,
    period_label    TEXT NOT NULL DEFAULT '',
    total_per_unit  NUMERIC CHECK (total_per_unit IS NULL OR total_per_unit >= 0),  -- NULL = amount unavailable
    include_flag    INTEGER NOT NULL CHECK (include_flag IN (0,1)),
    amount_grade    TEXT NOT NULL CHECK (amount_grade IN ('EXCHANGE','ISSUER','REGULATOR','AGGREGATOR','UNKNOWN')),
    source_id       TEXT REFERENCES source(source_id),
    document_id     TEXT REFERENCES source_document(document_id),
    status_text     TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    review_status   TEXT NOT NULL DEFAULT 'OK' CHECK (review_status IN ('OK','NEEDS_REVIEW')),
    run_id          TEXT REFERENCES import_run(run_id),
    retrieved_at    TEXT,
    CHECK (include_flag = 0 OR total_per_unit IS NOT NULL)   -- an included row must have an amount
);
CREATE INDEX ix_distribution_event_key_ex ON distribution_event (instrument_key, ex_date);

CREATE TABLE distribution_component (
    event_id        TEXT NOT NULL REFERENCES distribution_event(event_id),
    component_type  TEXT NOT NULL CHECK (component_type IN ('INTEREST','DIVIDEND','RENTAL','OTHER_INCOME','CAPITAL_REPAYMENT')),
    amount          NUMERIC NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (event_id, component_type)
);

CREATE TABLE index_level (            -- benchmark levels for tracking difference; licence NOT cleared
    index_key   TEXT NOT NULL,
    level_date  DATE NOT NULL,
    level       NUMERIC NOT NULL CHECK (level > 0),
    source_id   TEXT REFERENCES source(source_id),
    PRIMARY KEY (index_key, level_date)
);

CREATE TABLE holding (                -- ETF portfolio disclosures (schema only in M1; no calculations yet)
    etf_key     TEXT NOT NULL REFERENCES instrument(instrument_key),
    as_of_date  DATE NOT NULL,
    isin        TEXT NOT NULL,
    name        TEXT NOT NULL,
    weight      NUMERIC NOT NULL CHECK (weight >= 0 AND weight <= 1),
    source_id   TEXT REFERENCES source(source_id),
    PRIMARY KEY (etf_key, as_of_date, isin)
);

CREATE TABLE fundamental (            -- typed curated fields: occupancy, WALE, NDCF, concession life, expense ratio...
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    metric_key      TEXT NOT NULL,
    period_end      DATE NOT NULL,
    value           NUMERIC,
    unit            TEXT NOT NULL DEFAULT '',
    definition      TEXT NOT NULL DEFAULT '',
    grade           TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (grade IN ('EXCHANGE','ISSUER','REGULATOR','AGGREGATOR','UNKNOWN')),
    source_id       TEXT REFERENCES source(source_id),
    PRIMARY KEY (instrument_key, metric_key, period_end)
);

-- ---- M2: acquisition audit, freshness and discrepancy handling ---------------------------------------------
CREATE TABLE retrieval_log (          -- one row per source per attempt, INCLUDING skipped and failed attempts
    retrieval_id     TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL REFERENCES source(source_id),
    started_at       TEXT NOT NULL,   -- UTC ISO-8601 retrieval time
    finished_at      TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('OK','NO_NEW_DATA','SKIPPED_NOT_CLEARED','SKIPPED_DISABLED',
                                                     'SKIPPED_NOT_DUE','SKIPPED_OUTSIDE_SESSION','ERROR')),
    window_class     TEXT NOT NULL DEFAULT 'local' CHECK (window_class IN ('market','daily','local')),
    note             TEXT NOT NULL DEFAULT '',   -- schedule reason, e.g. HOLIDAY: Dussehra
    attempts         INTEGER NOT NULL DEFAULT 0,
    documents        INTEGER NOT NULL DEFAULT 0,
    rows_accepted    INTEGER NOT NULL DEFAULT 0,
    rows_rejected    INTEGER NOT NULL DEFAULT 0,
    observed_through DATE,            -- latest market-observation date contained in the data (NOT the retrieval date)
    error            TEXT
);
CREATE INDEX ix_retrieval_log_source ON retrieval_log (source_id, started_at);

CREATE TABLE discrepancy (            -- cross-source disagreement; both observations are kept, nothing is overwritten
    instrument_key  TEXT NOT NULL REFERENCES instrument(instrument_key),
    field           TEXT NOT NULL CHECK (field IN ('price','nav','distribution','leverage')),
    ref_date        DATE NOT NULL,
    source_a        TEXT NOT NULL,
    value_a         TEXT NOT NULL,
    source_b        TEXT NOT NULL,
    value_b         TEXT NOT NULL,
    abs_diff        TEXT NOT NULL,
    detected_at     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED')),
    resolution_note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (instrument_key, field, ref_date, source_a, source_b)
);

CREATE TABLE news_item (              -- announcements/news headlines; display needs the source to be display_cleared
    news_id         TEXT PRIMARY KEY,           -- content hash
    published_at    TEXT NOT NULL,              -- UTC ISO-8601, when the item was published (observation time)
    retrieved_at    TEXT,                       -- UTC ISO-8601, when we fetched it
    source_id       TEXT NOT NULL REFERENCES source(source_id),
    publisher       TEXT NOT NULL DEFAULT '',   -- original publisher / filing type as stated by the source
    category        TEXT NOT NULL CHECK (category IN ('REIT','INVIT','INFRASTRUCTURE','CORPORATE','OTHER')),
    instrument_key  TEXT REFERENCES instrument(instrument_key),
    headline        TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL DEFAULT '' CHECK (url = '' OR url LIKE 'http://%' OR url LIKE 'https://%'),
    document_id     TEXT REFERENCES source_document(document_id)
);
CREATE INDEX ix_news_published ON news_item (published_at);
