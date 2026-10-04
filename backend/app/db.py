from functools import lru_cache
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache
def get_engine():
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine(), expire_on_commit=False) as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
