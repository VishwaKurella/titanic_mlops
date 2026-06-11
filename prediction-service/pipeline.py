import pandas as pd
import numpy as np
from sklearn.linear_model import SGDClassifier, LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder, FunctionTransformer
from sklearn.impute import SimpleImputer
from xgboost import XGBClassifier

# ── Column groups ──────────────────────────────────────────────────────────────

RAW_INPUT_COLS       = ["Pclass", "Sex", "Age", "Fare", "Embarked", "Name", "SibSp", "Parch"]
NUMERIC_FEATURES     = ["Age", "Fare", "Pclass", "FamilySize"]
CATEGORICAL_FEATURES = ["Sex", "Embarked", "Title", "FareBand", "IsAlone"]
FEATURES             = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET               = "Survived"
DEFAULT_DATASET      = "/shared/datasets/Titanic-Dataset.csv"

# ── Model type registry ────────────────────────────────────────────────────────
# Single source of truth for supported types and their capabilities.
# Add new classifiers here — nothing else needs changing.

MODEL_REGISTRY = {
    "SGDClassifier": {
        "supports_partial_fit": True,
        "description": "Linear classifier with stochastic gradient descent. Fast, supports incremental training.",
    },
    "RandomForestClassifier": {
        "supports_partial_fit": False,
        "description": "Ensemble of decision trees. Best out-of-the-box accuracy, no incremental training.",
    },
    "LogisticRegression": {
        "supports_partial_fit": False,
        "description": "Linear classifier with L-BFGS optimiser. Stable, interpretable, good baseline.",
    },
    "XGBoost": {
        "supports_partial_fit": False,
        "description": "Gradient boosted decision trees. High accuracy on structured/tabular data.",
    }
}

SUPPORTED_MODELS        = list(MODEL_REGISTRY.keys())
INCREMENTAL_MODELS      = [k for k, v in MODEL_REGISTRY.items() if v["supports_partial_fit"]]
DEFAULT_MODEL_TYPE      = "SGDClassifier"


def supports_partial_fit(model_type: str) -> bool:
    return MODEL_REGISTRY.get(model_type, {}).get("supports_partial_fit", False)


# ── Title extraction ───────────────────────────────────────────────────────────

TITLE_MAP = {
    "Mr": "Mr", "Mrs": "Mrs", "Miss": "Miss", "Master": "Master",
    "Col": "Rare", "Major": "Rare", "Dr": "Rare", "Rev": "Rare", "Capt": "Rare",
    "Mme": "Mrs", "Ms": "Miss", "Lady": "Rare", "Mlle": "Miss",
    "Sir": "Rare", "Countess": "Rare", "Jonkheer": "Rare", "Don": "Rare",
}


def extract_title(name: str) -> str:
    import re
    if not isinstance(name, str) or not name.strip():
        return ""
    match = re.search(r",\s*([^\.]+)\.", name)
    if not match:
        return ""
    return TITLE_MAP.get(match.group(1).strip(), "Rare")


def infer_title(sex: str, age) -> str:
    is_female = str(sex).strip().lower() == "female"
    try:
        is_minor = float(age) < 18
    except (TypeError, ValueError):
        is_minor = False
    if is_female:
        return "Miss" if is_minor else "Mrs"
    return "Master" if is_minor else "Mr"


# ── Feature engineering ────────────────────────────────────────────────────────

def feature_engineer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Title
    if "Name" in df.columns:
        df["Title"] = df["Name"].apply(extract_title)
        mask = df["Title"] == ""
        if mask.any():
            df.loc[mask, "Title"] = df[mask].apply(
                lambda r: infer_title(r.get("Sex", ""), r.get("Age", None)), axis=1
            )
    else:
        df["Title"] = df.apply(
            lambda r: infer_title(r.get("Sex", ""), r.get("Age", None)), axis=1
        )

    # FamilySize + IsAlone
    sibsp = pd.to_numeric(df.get("SibSp", 0), errors="coerce").fillna(0)
    parch = pd.to_numeric(df.get("Parch", 0), errors="coerce").fillna(0)
    df["FamilySize"] = sibsp + parch + 1
    df["IsAlone"]    = (df["FamilySize"] == 1).map({True: "Yes", False: "No"})

    # FareBand
    fare = pd.to_numeric(df.get("Fare", None), errors="coerce")
    try:
        df["FareBand"] = pd.qcut(
            fare, q=4,
            labels=["Low", "Mid", "High", "Very_High"],
            duplicates="drop",
        ).astype(str)
    except ValueError:
        def fare_label(f):
            try:
                f = float(f)
            except (TypeError, ValueError):
                return "Mid"
            if f <= 7.9:  return "Low"
            if f <= 14.5: return "Mid"
            if f <= 31.3: return "High"
            return "Very_High"
        df["FareBand"] = fare.apply(fare_label)

    return df[FEATURES]


# ── Pipeline factory ───────────────────────────────────────────────────────────

def _build_preprocessor() -> ColumnTransformer:
    """Shared preprocessor — identical for all classifier types."""
    num_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", num_pipe, NUMERIC_FEATURES),
        ("cat", cat_pipe, CATEGORICAL_FEATURES),
    ])


def _build_classifier(model_type: str):
    """Return a fresh, unfitted classifier for the given type."""
    if model_type == "SGDClassifier":
        return SGDClassifier(loss="log_loss", random_state=42)
    if model_type == "RandomForestClassifier":
        # n_estimators=200 for solid accuracy; n_jobs=-1 uses all cores
        return RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    if model_type == "LogisticRegression":
        # max_iter=1000 — default 100 often doesn't converge on Titanic
        return LogisticRegression(max_iter=1000, random_state=42)
    if model_type == "XGBoost":
        return XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,)
    raise ValueError(
        f"Unsupported model_type '{model_type}'. "
        f"Choose from: {SUPPORTED_MODELS}"
    )


def build_pipeline(model_type: str = DEFAULT_MODEL_TYPE) -> Pipeline:
    """
    Build a full sklearn Pipeline for the given classifier type.
    Steps: engineer → preprocessor → classifier
    """
    if model_type not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unknown model_type '{model_type}'. "
            f"Supported: {SUPPORTED_MODELS}"
        )
    return Pipeline([
        ("engineer",     FunctionTransformer(feature_engineer, validate=False)),
        ("preprocessor", _build_preprocessor()),
        ("classifier",   _build_classifier(model_type)),
    ])