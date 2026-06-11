from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
import pandas as pd, joblib, os, time, requests

from db      import get_db, Model, TrainingRun
from schemas import TrainRequest, TrainResponse
from pipeline import (
    build_pipeline, RAW_INPUT_COLS, TARGET, DEFAULT_DATASET,
    SUPPORTED_MODELS, INCREMENTAL_MODELS, supports_partial_fit,
)

CONFIG_CACHE = {}

app = FastAPI()

@app.on_event("startup")
def startup():
    db = SessionLocal()

    try:
        load_general_config(db)
    finally:
        db.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ── helpers ────────────────────────────────────────────────────────────────────

def parse_value(value: str, value_type: str):
    if value_type == "int":
        return int(value)

    if value_type == "float":
        return float(value)

    return value


def load_general_config(db: Session):
    global CONFIG_CACHE

    rows = db.query(GeneralConfig).all()

    CONFIG_CACHE = {
        row.key: parse_value(row.value, row.value_type)
        for row in rows
    }

    return CONFIG_CACHE


def get_config(key: str, default=None):
    return CONFIG_CACHE.get(key, default)

def load_dataframe(data: list[dict] | None) -> pd.DataFrame:
    if data:
        return pd.DataFrame(data)
    if not os.path.exists(DEFAULT_DATASET):
        raise HTTPException(500, "No data posted and default dataset not found")
    return pd.read_csv(DEFAULT_DATASET)


def compute_metrics(model, X, y) -> dict:
    preds = model.predict(X)
    return {
        "accuracy":  float(accuracy_score(y, preds)),
        "f1":        float(f1_score(y, preds,        zero_division=0)),
        "precision": float(precision_score(y, preds, zero_division=0)),
        "recall":    float(recall_score(y, preds,    zero_division=0)),
    }


def next_version(model_type: str) -> str:
    # Include model type in name so you can identify it at a glance
    short = model_type.replace("Classifier", "").replace("Regression", "Reg")
    return f"model_{short}_{int(time.time())}"


def save_pkl(model, name: str) -> str:
    path = os.path.join(CONFIG_CACHE.get("models_directory"), f"{name}.pkl")
    joblib.dump(model, path)
    return path


def notify_prediction_service():
    try:
        requests.post("http://prediction-service:8000/reload", timeout=3)
    except Exception:
        pass


# ── POST /train ────────────────────────────────────────────────────────────────

@app.post("/train", response_model=TrainResponse)
def train(request: TrainRequest, db: Session = Depends(get_db)):
    start      = time.time()
    model_type = request.model_type or "SGDClassifier"

    df = load_dataframe(request.data)
    if TARGET not in df.columns:
        raise HTTPException(422, f"Dataset must include '{TARGET}' column")

    X, y = df[[c for c in RAW_INPUT_COLS if c in df.columns]], df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y
    )

    model = build_pipeline(model_type)
    model.fit(X_train, y_train)

    train_metrics = compute_metrics(model, X_train, y_train)
    test_metrics  = compute_metrics(model, X_test,  y_test)
    duration      = round(time.time() - start, 3)
    name          = request.model_name or next_version(model_type)

    save_pkl(model, name)

    db.query(Model).filter(Model.active == True).update({"active": False})
    record = Model(
        model_name      = name,
        active          = True,
        model_type      = model_type,
        train_accuracy  = train_metrics["accuracy"],
        train_f1        = train_metrics["f1"],
        train_precision = train_metrics["precision"],
        train_recall    = train_metrics["recall"],
        test_accuracy   = test_metrics["accuracy"],
        test_f1         = test_metrics["f1"],
        test_precision  = test_metrics["precision"],
        test_recall     = test_metrics["recall"],
        training_rows   = len(X_train),
        test_rows       = len(X_test),
    )
    db.add(record)
    db.flush()

    db.add(TrainingRun(
        model_id       = record.id,
        triggered_by   = request.user_id,
        run_type       = "full",
        train_accuracy = train_metrics["accuracy"],
        train_f1       = train_metrics["f1"],
        test_accuracy  = test_metrics["accuracy"],
        test_f1        = test_metrics["f1"],
        duration_secs  = duration,
        training_rows  = len(X_train),
        test_rows      = len(X_test),
    ))
    db.commit()
    notify_prediction_service()

    return TrainResponse(
        status          = "trained",
        model_name      = name,
        model_type      = model_type,
        run_type        = "full",
        train_accuracy  = train_metrics["accuracy"],
        train_f1        = train_metrics["f1"],
        train_precision = train_metrics["precision"],
        train_recall    = train_metrics["recall"],
        test_accuracy   = test_metrics["accuracy"],
        test_f1         = test_metrics["f1"],
        test_precision  = test_metrics["precision"],
        test_recall     = test_metrics["recall"],
        training_rows   = len(X_train),
        test_rows       = len(X_test),
        duration_secs   = duration,
    )


# ── POST /incremental-train ───────────────────────────────────────────────────

@app.post("/incremental-train", response_model=TrainResponse)
def incremental_train(request: TrainRequest, db: Session = Depends(get_db)):
    start = time.time()

    # Resolve base model record
    if request.model_name:
        record = db.query(Model).filter(Model.model_name == request.model_name).first()
        if not record:
            raise HTTPException(404, f"Model '{request.model_name}' not found")
    else:
        record = db.query(Model).filter(Model.active == True).first()
        if not record:
            raise HTTPException(503, "No active model — call /initBaseModel first")

    # ── Industry-standard: block partial_fit for non-SGD models ───────────────
    # RandomForest and LogisticRegression don't support partial_fit.
    # A silent full-retrain on a subset of data would be worse than either
    # a proper full retrain or an explicit error. Fail fast instead.
    if not supports_partial_fit(record.model_type):
        raise HTTPException(
            400,
            f"Model type '{record.model_type}' does not support incremental training. "
            f"Only {INCREMENTAL_MODELS} support partial_fit(). "
            f"Use POST /train to do a full retrain instead."
        )

    pkl_path = os.path.join(MODELS_DIR, f"{record.model_name}.pkl")
    if not os.path.exists(pkl_path):
        raise HTTPException(404, f"Model file missing: {pkl_path}")

    df = load_dataframe(request.data)
    if TARGET not in df.columns:
        raise HTTPException(422, f"Dataset must include '{TARGET}' column")

    X, y = df[[c for c in RAW_INPUT_COLS if c in df.columns]], df[TARGET]
    if len(df) >= 10:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y
        )
    else:
        X_train, X_test, y_train, y_test = X, X, y, y

    model = joblib.load(pkl_path)

    engineered  = model.named_steps["engineer"].transform(X_train)
    transformed = model.named_steps["preprocessor"].transform(engineered)
    model.named_steps["classifier"].partial_fit(transformed, y_train, classes=[0, 1])

    train_metrics = compute_metrics(model, X_train, y_train)
    test_metrics  = compute_metrics(model, X_test,  y_test)
    duration      = round(time.time() - start, 3)
    new_name      = f"{record.model_name}_inc_{int(time.time())}"

    save_pkl(model, new_name)

    db.query(Model).filter(Model.active == True).update({"active": False})
    new_record = Model(
        model_name      = new_name,
        active          = True,
        model_type      = record.model_type,
        train_accuracy  = train_metrics["accuracy"],
        train_f1        = train_metrics["f1"],
        train_precision = train_metrics["precision"],
        train_recall    = train_metrics["recall"],
        test_accuracy   = test_metrics["accuracy"],
        test_f1         = test_metrics["f1"],
        test_precision  = test_metrics["precision"],
        test_recall     = test_metrics["recall"],
        training_rows   = len(X_train),
        test_rows       = len(X_test),
    )
    db.add(new_record)
    db.flush()

    db.add(TrainingRun(
        model_id       = new_record.id,
        triggered_by   = request.user_id,
        run_type       = "incremental",
        train_accuracy = train_metrics["accuracy"],
        train_f1       = train_metrics["f1"],
        test_accuracy  = test_metrics["accuracy"],
        test_f1        = test_metrics["f1"],
        duration_secs  = duration,
        training_rows  = len(X_train),
        test_rows      = len(X_test),
    ))
    db.commit()
    notify_prediction_service()

    return TrainResponse(
        status          = "incrementally trained",
        model_name      = new_name,
        model_type      = record.model_type,
        run_type        = "incremental",
        train_accuracy  = train_metrics["accuracy"],
        train_f1        = train_metrics["f1"],
        train_precision = train_metrics["precision"],
        train_recall    = train_metrics["recall"],
        test_accuracy   = test_metrics["accuracy"],
        test_f1         = test_metrics["f1"],
        test_precision  = test_metrics["precision"],
        test_recall     = test_metrics["recall"],
        training_rows   = len(X_train),
        test_rows       = len(X_test),
        duration_secs   = duration,
    )


# ── GET /models ───────────────────────────────────────────────────────────────

@app.get("/models")
def list_models(db: Session = Depends(get_db)):
    models = db.query(Model).order_by(Model.created_at.desc()).all()
    return [
        {
            "id":             str(m.id),
            "model_name":     m.model_name,
            "model_type":     m.model_type,
            "active":         m.active,
            "train_accuracy": m.train_accuracy,
            "train_f1":       m.train_f1,
            "test_accuracy":  m.test_accuracy,
            "test_f1":        m.test_f1,
            "training_rows":  m.training_rows,
            "test_rows":      m.test_rows,
            "created_at":     m.created_at.isoformat(),
        }
        for m in models
    ]


# ── GET /training-runs ────────────────────────────────────────────────────────

@app.get("/training-runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(50).all()
    return [
        {
            "id":             str(r.id),
            "model_id":       str(r.model_id),
            "triggered_by":   r.triggered_by,
            "run_type":       r.run_type,
            "train_accuracy": r.train_accuracy,
            "train_f1":       r.train_f1,
            "test_accuracy":  r.test_accuracy,
            "test_f1":        r.test_f1,
            "duration_secs":  r.duration_secs,
            "training_rows":  r.training_rows,
            "test_rows":      r.test_rows,
            "created_at":     r.created_at.isoformat(),
        }
        for r in runs
    ]


# ── GET /supported-models — useful for the dashboard dropdown ─────────────────

@app.get("/supported-models")
def supported_models():
    from pipeline import MODEL_REGISTRY
    return MODEL_REGISTRY


@app.post("/refresh")
def reload_config(db: Session = Depends(get_db)):
    global CONFIG_CACHE
    CONFIG_CACHE = load_general_config(db)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    active = db.query(Model).filter(Model.active == True).first()
    return {
        "status":       "ok",
        "active_model": active.model_name if active else None,
        "active_type":  active.model_type if active else None,
    }