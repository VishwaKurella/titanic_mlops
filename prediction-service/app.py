from fastapi import FastAPI

import pandas as pd
import joblib
import json
import os

app = FastAPI()

MODELS_DIR = "/shared/models"
METADATA_PATH = "/shared/metadata/models.json"

# ======================================================
# LOAD ACTIVE MODEL
# ======================================================

def get_active_model():

    with open(METADATA_PATH, "r") as f:

        metadata = json.load(f)

    active_model = metadata["active_model"]

    if active_model is None:

        return None

    model_path = os.path.join(
        MODELS_DIR,
        active_model
    )

    return joblib.load(model_path)

# ======================================================
# PREDICT
# ======================================================

@app.post("/predict")

def predict(data: dict):

    model = get_active_model()

    if model is None:

        return {
            "error": "no active model"
        }

    df = pd.DataFrame([data])

    prediction = model.predict(df)

    probability = model.predict_proba(df)

    return {

        "prediction": int(prediction[0]),

        "probability": float(probability[0][1])
    }