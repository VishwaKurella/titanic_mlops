from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
import pandas as pd, joblib, os, time, requests

from db       import get_db, Model, TrainingRun
from schemas  import TrainRequest, TrainResponse
from pipeline import build_pipeline, FEATURES, TARGET, DEFAULT_DATASET

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODELS_DIR = "/shared/models"
os.makedirs(MODELS_DIR, exist_ok=True)

# ── helpers ────────────────────────────────────────────────────────────────────

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
        "f1_score":  float(f1_score(y, preds,  zero_division=0)),
        "precision": float(precision_score(y, preds, zero_division=0)),
        "recall":    float(recall_score(y, preds,    zero_division=0)),
    }

def next_version() -> str:
    # Timestamp-based — avoids COUNT() race condition
    return f"model_v{int(time.time())}"

def save_pkl(model, name: str) -> str:
    path = os.path.join(MODELS_DIR, f"{name}.pkl")
    joblib.dump(model, path)
    return path

def notify_prediction_service():
    try:
        requests.post("http://prediction-service:8000/reload", timeout=3)
    except Exception:
        pass  # non-fatal

# ── POST /train  (full retrain from scratch) ──────────────────────────────────

@app.post("/train", response_model=TrainResponse)
def train(request: TrainRequest, db: Session = Depends(get_db)):
    start = time.time()

    df = load_dataframe(request.data)
    if TARGET not in df.columns:
        raise HTTPException(422, f"Dataset must include '{TARGET}' column")

    X, y  = df[FEATURES], df[TARGET]
    model = build_pipeline()
    model.fit(X, y)

    metrics  = compute_metrics(model, X, y)
    duration = round(time.time() - start, 3)
    name     = request.model_name or next_version()

    # ── CRITICAL: save file BEFORE committing to DB ──────────────────────────
    # If disk write fails we raise before touching the DB — no phantom records
    save_pkl(model, name)

    db.query(Model).filter(Model.active == True).update({"active": False})

    record = Model(
        model_name    = name,
        active        = True,
        training_rows = len(df),
        **metrics,
    )
    db.add(record)
    db.flush()

    db.add(TrainingRun(
        model_id      = record.id,
        triggered_by  = request.user_id,
        dataset_rows  = len(df),
        duration_secs = duration,
        run_type      = "full",
        accuracy      = metrics["accuracy"],
        f1_score      = metrics["f1_score"],
    ))
    db.commit()

    notify_prediction_service()

    return TrainResponse(
        status        = "trained",
        model_name    = name,
        run_type      = "full",
        training_rows = len(df),
        duration_secs = duration,
        **metrics,
    )

# ── POST /incremental-train ───────────────────────────────────────────────────

@app.post("/incremental-train", response_model=TrainResponse)
def incremental_train(request: TrainRequest, db: Session = Depends(get_db)):
    start = time.time()

    # Resolve base model
    if request.model_name:
        record = db.query(Model).filter(Model.model_name == request.model_name).first()
        if not record:
            raise HTTPException(404, f"Model '{request.model_name}' not found")
    else:
        record = db.query(Model).filter(Model.active == True).first()
        if not record:
            raise HTTPException(503, "No active model — call /initBaseModel first")

    pkl_path = os.path.join(MODELS_DIR, f"{record.model_name}.pkl")
    if not os.path.exists(pkl_path):
        raise HTTPException(404, f"Model file missing: {pkl_path}")

    df = load_dataframe(request.data)
    if TARGET not in df.columns:
        raise HTTPException(422, f"Dataset must include '{TARGET}' column")

    X, y  = df[FEATURES], df[TARGET]
    model = joblib.load(pkl_path)

    transformed = model.named_steps["preprocessor"].transform(X)
    model.named_steps["classifier"].partial_fit(transformed, y, classes=[0, 1])

    metrics  = compute_metrics(model, X, y)
    duration = round(time.time() - start, 3)
    new_name = f"{record.model_name}_inc_{int(time.time())}"

    # ── save file BEFORE DB commit ────────────────────────────────────────────
    save_pkl(model, new_name)

    db.query(Model).filter(Model.active == True).update({"active": False})

    new_record = Model(
        model_name    = new_name,
        active        = True,
        training_rows = len(df),
        **metrics,
    )
    db.add(new_record)
    db.flush()

    db.add(TrainingRun(
        model_id      = new_record.id,
        triggered_by  = request.user_id,
        dataset_rows  = len(df),
        duration_secs = duration,
        run_type      = "incremental",
        accuracy      = metrics["accuracy"],
        f1_score      = metrics["f1_score"],
    ))
    db.commit()

    notify_prediction_service()

    return TrainResponse(
        status        = "incrementally trained",
        model_name    = new_name,
        run_type      = "incremental",
        training_rows = len(df),
        duration_secs = duration,
        **metrics,
    )

# ── GET /models ───────────────────────────────────────────────────────────────

@app.get("/models")
def list_models(db: Session = Depends(get_db)):
    models = db.query(Model).order_by(Model.created_at.desc()).all()
    return [
        {
            "id":            str(m.id),
            "model_name":    m.model_name,
            "active":        m.active,
            "accuracy":      m.accuracy,
            "f1_score":      m.f1_score,
            "precision":     m.precision,
            "recall":        m.recall,
            "training_rows": m.training_rows,
            "created_at":    m.created_at.isoformat(),
        }
        for m in models
    ]

# ── GET /training-runs ────────────────────────────────────────────────────────

@app.get("/training-runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(50).all()
    return [
        {
            "id":            str(r.id),
            "model_id":      str(r.model_id),
            "triggered_by":  r.triggered_by,
            "run_type":      r.run_type,
            "accuracy":      r.accuracy,
            "f1_score":      r.f1_score,
            "duration_secs": r.duration_secs,
            "dataset_rows":  r.dataset_rows,
            "created_at":    r.created_at.isoformat(),
        }
        for r in runs
    ]

@app.get("/health")
def health(db: Session = Depends(get_db)):
    active = db.query(Model).filter(Model.active == True).first()
    return {
        "status":       "ok",
        "active_model": active.model_name if active else None,
    }