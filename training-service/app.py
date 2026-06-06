from fastapi import FastAPI
from sklearn.linear_model import SGDClassifier

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer

from sklearn.preprocessing import (
    StandardScaler,
    OneHotEncoder
)

from sklearn.impute import SimpleImputer

from sklearn.metrics import accuracy_score

import pandas as pd
import joblib
import json
import os
import time

app = FastAPI()

MODELS_DIR = "/shared/models"
METADATA_PATH = "/shared/metadata/models.json"

# ======================================================
# CREATE MODEL PIPELINE
# ======================================================

numeric_features = [
    "Age",
    "Fare",
    "Pclass"
]

categorical_features = [
    "Sex",
    "Embarked"
]

numeric_transformer = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler())
])

categorical_transformer = Pipeline([
    ("imputer", SimpleImputer(strategy="most_frequent")),
    ("encoder", OneHotEncoder(handle_unknown="ignore"))
])

preprocessor = ColumnTransformer([
    ("num", numeric_transformer, numeric_features),
    ("cat", categorical_transformer, categorical_features)
])

# ======================================================
# LOAD METADATA
# ======================================================

def load_metadata():

    with open(METADATA_PATH, "r") as f:

        return json.load(f)

# ======================================================
# SAVE METADATA
# ======================================================

def save_metadata(data):

    with open(METADATA_PATH, "w") as f:

        json.dump(data, f, indent=2)

# ======================================================
# TRAIN NEW MODEL
# ======================================================

@app.post("/train")

def train():

    df = pd.read_csv(
        "/shared/datasets/Titanic-Dataset.csv"
    )

    X = df[[
        "Pclass",
        "Sex",
        "Age",
        "Fare",
        "Embarked"
    ]]

    y = df["Survived"]

    classifier = SGDClassifier(
        loss="log_loss"
    )

    model = Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", classifier)
    ])

    model.fit(X, y)

    predictions = model.predict(X)

    accuracy = accuracy_score(y, predictions)

    metadata = load_metadata()

    version = len(metadata["models"]) + 1

    model_name = f"model_v{version}.pkl"

    model_path = os.path.join(
        MODELS_DIR,
        model_name
    )

    joblib.dump(model, model_path)

    metadata["models"].append({

        "name": model_name,

        "accuracy": float(accuracy),

        "created_at": time.time()
    })

    # First model becomes active automatically

    if metadata["active_model"] is None:

        metadata["active_model"] = model_name

    save_metadata(metadata)

    return {

        "status": "trained",

        "model": model_name,

        "accuracy": accuracy
    }

# ======================================================
# GET MODELS
# ======================================================

@app.get("/models")

def get_models():

    return load_metadata()

# ======================================================
# ACTIVATE MODEL
# ======================================================

@app.post("/activate/{model_name}")

def activate_model(model_name: str):

    metadata = load_metadata()

    metadata["active_model"] = model_name

    save_metadata(metadata)

    return {

        "status": "activated",

        "model": model_name
    }

@app.post("/incremental-train/{model_name}")

def incremental_train(model_name: str):

    model_path = os.path.join(
        MODELS_DIR,
        model_name
    )

    model = joblib.load(model_path)

    df = pd.read_csv(
        "/shared/datasets/Titanic-Dataset.csv"
    )

    X = df[[
        "Pclass",
        "Sex",
        "Age",
        "Fare",
        "Embarked"
    ]]

    y = df["Survived"]

    transformed = model.named_steps[
        "preprocessor"
    ].transform(X)

    classifier = model.named_steps[
        "classifier"
    ]

    classifier.partial_fit(
        transformed,
        y
    )

    new_version = f"{model_name}_updated.pkl"

    new_path = os.path.join(
        MODELS_DIR,
        new_version
    )

    joblib.dump(model, new_path)

    return {
        "status": "incrementally trained",
        "new_model": new_version
    }