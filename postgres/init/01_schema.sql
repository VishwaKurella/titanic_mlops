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
    id             UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name     TEXT         NOT NULL UNIQUE,
    active         BOOLEAN      NOT NULL DEFAULT FALSE,

    -- Training-set metrics (optimistic — model has seen this data)
    train_accuracy FLOAT,
    train_f1       FLOAT,
    train_precision FLOAT,
    train_recall   FLOAT,

    -- Test-set metrics (honest — held-out 20%)
    test_accuracy  FLOAT,
    test_f1        FLOAT,
    test_precision FLOAT,
    test_recall    FLOAT,

    training_rows  INTEGER,   -- rows used for training (80%)
    test_rows      INTEGER,   -- rows used for evaluation (20%)

    model_type     VARCHAR(100) NOT NULL DEFAULT 'SGDClassifier',
    triggered_by   TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Enforce only one active model at the DB level
CREATE UNIQUE INDEX one_active_model
    ON models (active)
    WHERE active = TRUE;

-- ======================================================
-- TRAINING RUNS  (audit trail)
-- ======================================================
CREATE TABLE training_runs (
    id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_id       UUID        NOT NULL REFERENCES models(id),
    triggered_by   TEXT,
    run_type       TEXT        NOT NULL,   -- 'full' | 'incremental'

    -- Both sets logged per run so you can track overfitting over time
    train_accuracy FLOAT,
    train_f1       FLOAT,
    test_accuracy  FLOAT,
    test_f1        FLOAT,

    duration_secs  FLOAT,
    training_rows  INTEGER,
    test_rows      INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- general_configuration
-- Key-value store for platform-wide runtime settings.
-- Services cache this at startup; POST /config/reload refreshes the cache.
-- NEVER store secrets here — secrets stay in .env.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS general_configuration (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    key         TEXT        NOT NULL UNIQUE,
    value       TEXT        NOT NULL,
    value_type  TEXT        NOT NULL CHECK (value_type IN ('int', 'float', 'string')),
    description TEXT,
    updated_by  TEXT, 
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
 
 
-- ---------------------------------------------------------------------------
-- training_configurations
-- Named presets that control how a model is trained.
-- Core params are typed columns (queryable, comparable across runs).
-- Model-specific hyperparameters go in extra_params JSONB.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS training_configurations (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    config_name  TEXT        NOT NULL UNIQUE,
    description  TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT FALSE,
 
    -- Core training params (typed — always present, always queryable)
    model_type   TEXT        NOT NULL DEFAULT 'SGDClassifier',
    cv_folds     INTEGER     NOT NULL DEFAULT 0,   -- 0 = disabled; >0 = cross_val_score folds
    class_weight TEXT        NOT NULL DEFAULT 'none', -- 'none' | 'balanced'
 
    -- Model-specific hyperparameters (flexible — no migration needed for new params)
    -- Example: {"loss": "log_loss", "alpha": 0.0001, "max_iter": 1000}
    extra_params JSONB       NOT NULL DEFAULT '{}',
 
    created_by   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
 
-- Only one training configuration may be active at a time
CREATE UNIQUE INDEX IF NOT EXISTS one_active_training_config
    ON training_configurations (is_active)
    WHERE is_active = TRUE;
 