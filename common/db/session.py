# common/db/session.py
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from common.config import DB_CONFIG

logger = logging.getLogger(__name__)

# Create the database URL from config
DATABASE_URL = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"

# Create engine and session factory with connection pooling settings
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get a database session"""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Session context manager to ensure proper closing"""
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


# Create a function to get db in a dependency-injection manner for FastAPI
def get_db_dependency():
    """Get a database session for dependency injection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()