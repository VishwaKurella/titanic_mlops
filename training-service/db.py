from sqlalchemy import create_engine, Column, String, Boolean, Float, Integer, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid, os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@postgres/mlplatform")
engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Model(Base):
    __tablename__ = "models"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name    = Column(String(250), unique=True, nullable=False)
    active        = Column(Boolean, default=False, nullable=False)
    accuracy      = Column(Float)
    f1_score      = Column(Float)
    precision     = Column(Float)
    recall        = Column(Float)
    training_rows = Column(Integer)
    model_type    = Column(String(100), default="SGDClassifier")
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    runs          = relationship("TrainingRun", back_populates="model")

class TrainingRun(Base):
    __tablename__ = "training_runs"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id      = Column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False)
    triggered_by  = Column(String, nullable=True)
    dataset_rows  = Column(Integer)
    accuracy      = Column(Float)
    f1_score      = Column(Float)
    duration_secs = Column(Float)
    run_type      = Column(String(50), nullable=False)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    model         = relationship("Model", back_populates="runs")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()