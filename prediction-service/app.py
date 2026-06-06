from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd, joblib, os

from db import get_db, Model

app        = FastAPI()
MODELS_DIR = "/shared/models"

# ── In-memory cache — avoids reloading .pkl on every request ──────────────────
_cache: dict = {"model": None, "name": None}

def get_active_model(db: Session):
    record = db.query(Model).filter(Model.active == True).first()
    if record is None:
        return None, None

    if _cache["name"] != record.model_name:
        path = os.path.join(MODELS_DIR, f"{record.model_name}.pkl")
        if not os.path.exists(path):
            raise HTTPException(404, f"Model file not found: {path}")
        _cache["model"] = joblib.load(path)
        _cache["name"]  = record.model_name

    return _cache["model"], record

# ── POST /predict ──────────────────────────────────────────────────────────────

@app.post("/predict")
def predict(data: dict, db: Session = Depends(get_db)):
    model, record = get_active_model(db)

    if model is None:
        raise HTTPException(503, "No active model — trigger /train first")

    try:
        df          = pd.DataFrame([data])
        prediction  = model.predict(df)
        probability = model.predict_proba(df)
    except Exception as e:
        raise HTTPException(422, f"Prediction failed: {str(e)}")

    return {
        "model_name":  record.model_name,
        "model_id":    str(record.id),
        "accuracy":    record.accuracy,
        "prediction":  int(prediction[0]),
        "probability": float(probability[0][1]),
    }

# ── POST /reload — called by training service after saving a new model ─────────

@app.post("/reload")
def reload():
    _cache["name"] = None  # next predict call will reload from disk
    return {"status": "cache cleared"}

# ── GET /health ────────────────────────────────────────────────────────────────

@app.get("/health")
def health(db: Session = Depends(get_db)):
    record = db.query(Model).filter(Model.active == True).first()
    return {
        "status":       "ok",
        "active_model": record.model_name if record else None,
    }