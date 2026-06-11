from sqlalchemy import (
    create_engine, Column, String, Boolean,
    Float, Integer, ForeignKey, DateTime, CheckConstraint
)
from sqlalchemy.orm import sessionmaker, DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

DATABASE_URL = "postgresql://admin:password@postgres/mlplatform"
engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Model(Base):
    __tablename__ = "models"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name     = Column(String(250), unique=True, nullable=False)
    active         = Column(Boolean, default=False, nullable=False)

    # Training-set metrics
    train_accuracy  = Column(Float)
    train_f1        = Column(Float)
    train_precision = Column(Float)
    train_recall    = Column(Float)

    # Test-set metrics (the honest numbers)
    test_accuracy   = Column(Float)
    test_f1         = Column(Float)
    test_precision  = Column(Float)
    test_recall     = Column(Float)

    training_rows  = Column(Integer)
    test_rows      = Column(Integer)
    model_type     = Column(String(100), default="SGDClassifier")
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    runs = relationship("TrainingRun", back_populates="model")


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id       = Column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False)
    triggered_by   = Column(String, nullable=True)
    run_type       = Column(String(50), nullable=False)

    train_accuracy = Column(Float)
    train_f1       = Column(Float)
    test_accuracy  = Column(Float)
    test_f1        = Column(Float)

    duration_secs  = Column(Float)
    training_rows  = Column(Integer)
    test_rows      = Column(Integer)
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    model = relationship("Model", back_populates="runs")

class GeneralConfig(Base):
    __tablename__ = "general_configuration"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key            = Column(String(50), unique=True, nullable=False)
    value          = Column(String, nullable=False)
    value_type     = Column(String, nullable=False)

    description    = Column(String, nullable=True)
    updated_by     = Column(String(50), nullable=True)

    updated_at     = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint(
            "value_type IN ('int', 'float', 'string')",
            name="check_value_type"
        ),
    )
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()