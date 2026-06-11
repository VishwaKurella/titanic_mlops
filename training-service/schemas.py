from pydantic import BaseModel, field_validator
from typing import Optional


class TrainRequest(BaseModel):
    data:       Optional[list[dict]] = None
    model_name: Optional[str]        = None
    user_id:    Optional[str]        = None
    model_type: Optional[str]        = "SGDClassifier"

    @field_validator("model_type")
    @classmethod
    def validate_model_type(cls, v):
        from pipeline import SUPPORTED_MODELS, DEFAULT_MODEL_TYPE
        if v is None:
            return DEFAULT_MODEL_TYPE
        if v not in SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model_type '{v}'. Choose from: {SUPPORTED_MODELS}"
            )
        return v


class TrainResponse(BaseModel):
    status:        str
    model_name:    str
    model_type:    str
    run_type:      str

    train_accuracy:  float
    train_f1:        float
    train_precision: float
    train_recall:    float

    test_accuracy:   float
    test_f1:         float
    test_precision:  float
    test_recall:     float

    training_rows: int
    test_rows:     int
    duration_secs: float