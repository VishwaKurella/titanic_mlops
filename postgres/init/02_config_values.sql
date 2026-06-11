 
-- Seed rows — INSERT only if the key does not yet exist so re-running
-- this script (e.g. after docker compose down -v) is idempotent.
INSERT INTO general_configuration (key, value, value_type, description, updated_by)
VALUES
    (
        'random_seed',
        '42',
        'int',
        'Global random seed used for train/test split and classifier initialisation. Change requires a retrain to take effect.',
        'ADMIN'
    ),
    (
        'test_split_ratio',
        '0.2',
        'float',
        'Proportion of training data held out for the test set (0.0-1.0). 0.2 = 80/20 split.',
        'ADMIN'
    ),
    (
        'default_model_type',
        'SGDClassifier',
        'string',
        'Classifier used when no training_configuration is specified. Must match a supported sklearn estimator name.',
        'ADMIN'
    ),
    (
        'rate_limit_rps',
        '20',
        'int',
        'Maximum requests per second per IP address on the gateway /predict route. Enforcement requires rate-limiting middleware.',
        'ADMIN'
    ),
    (
        'jwt_expiry_hours',
        '8',
        'int',
        'JWT token lifetime in hours. Tokens are hard-expired; no refresh is currently implemented.',
        'ADMIN'
    ),
    (
        "default_dataset",
        "full.csv",
        "string",
        "Extended titanic dataset",
        "ADMIN"
    ),
    (
        "models_directory",
        "/shared/models",
        "string",
        "All training models dataset directory",
        "ADMIN"
    )
ON CONFLICT (key) DO NOTHING;

-- Seed row — the default config that mirrors the previous hardcoded behaviour
INSERT INTO training_configurations (
    config_name,
    description,
    is_active,
    model_type,
    cv_folds,
    class_weight,
    extra_params,
    created_by
)
VALUES (
    'default',
    'Baseline SGDClassifier config. Mirrors the original hardcoded behaviour before DB-driven config was introduced.',
    TRUE,
    'SGDClassifier',
    0,
    'none',
    '{"loss": "log_loss", "max_iter": 1000}',
    'system'
)
ON CONFLICT (config_name) DO NOTHING;