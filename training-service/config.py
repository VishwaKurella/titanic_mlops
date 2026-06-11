from fastapi import HTTPException
from sqlalchemy.orm import Session

CONFIG_CACHE = {}


def parse_value(value: str, value_type: str):
    if value_type == "int":
        return int(value)

    if value_type == "float":
        return float(value)

    if value_type == "bool":
        return value.lower() == "true"

    return value


def load_config(db: Session):
    global CONFIG_CACHE

    rows = db.query(GeneralConfig).all()

    CONFIG_CACHE = {
        row.key: parse_value(row.value, row.value_type)
        for row in rows
    }

    validate_required_config()

    return CONFIG_CACHE


def validate_required_config():
    required_keys = [
        "models_directory",
        "test_split_ratio",
        "random_seed",
    ]

    missing = [key for key in required_keys if key not in CONFIG_CACHE]

    if missing:
        raise RuntimeError(
            f"Missing required config values: {missing}"
        )


def get_config(key: str):
    value = CONFIG_CACHE.get(key)

    if value is None:
        raise RuntimeError(
            f"Configuration key '{key}' not found"
        )

    return value