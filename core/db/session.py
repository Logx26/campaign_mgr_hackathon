"""SQLAlchemy session factory + FastAPI dependency."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings


_settings = get_settings()
_engine = create_engine(_settings.POSTGRES_DSN, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency. Use as `db: Session = Depends(get_db)`."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_engine():
    return _engine
