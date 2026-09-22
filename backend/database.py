"""
database.py — Koneksi SQLAlchemy ke PostgreSQL
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import get_settings

settings = get_settings()

# psycopg3 menggunakan prefix "postgresql+psycopg://"
db_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://")

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency untuk FastAPI — inject DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
