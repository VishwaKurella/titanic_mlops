from sqlalchemy import create_engine, Column, String, Boolean, Float, Integer, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid, os

DATABASE_URL = "postgresql://admin:password@postgres/mlplatform"
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
    training_rows = Column(Integer)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()