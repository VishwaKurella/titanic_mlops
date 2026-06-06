-- Drop all tables cleanly
DROP TABLE IF EXISTS training_runs CASCADE;
DROP TABLE IF EXISTS models        CASCADE;
DROP TABLE IF EXISTS users         CASCADE;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ======================================================
-- USERS
-- ======================================================
CREATE TABLE users (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      TEXT        NOT NULL UNIQUE,
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    role          TEXT        NOT NULL DEFAULT 'VIEWER',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ======================================================
-- MODELS
-- ======================================================
CREATE TABLE models (
    id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name    TEXT         NOT NULL UNIQUE,
    active        BOOLEAN      NOT NULL DEFAULT FALSE,
    accuracy      FLOAT,
    f1_score      FLOAT,
    precision     FLOAT,
    recall        FLOAT,
    training_rows INTEGER,
    model_type    VARCHAR(100) NOT NULL DEFAULT 'SGDClassifier',
    triggered_by  TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Enforce only one active model at the DB level
CREATE UNIQUE INDEX one_active_model
    ON models (active)
    WHERE active = TRUE;

-- ======================================================
-- TRAINING RUNS  (audit trail)
-- ======================================================
CREATE TABLE training_runs (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_id      UUID        NOT NULL REFERENCES models(id),
    triggered_by  TEXT,
    run_type      TEXT        NOT NULL,
    accuracy      FLOAT,
    f1_score      FLOAT,
    duration_secs FLOAT,
    dataset_rows  INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);