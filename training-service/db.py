from sqlalchemy import create_engine

DATABASE_URL = (
    "postgresql://admin:password@postgres/mlplatform"
)

engine = create_engine(DATABASE_URL)