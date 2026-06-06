from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class TrainRequest(BaseModel):
    data:       Optional[list[dict]] = None  # None = use default CSV
    model_name: Optional[str]        = None  # None = train on active model
    user_id:    Optional[str]        = None

class TrainResponse(BaseModel):
    status:        str
    model_name:    str
    run_type:      str
    accuracy:      float
    f1_score:      float
    precision:     float
    recall:        float
    training_rows: int
    duration_secs: float