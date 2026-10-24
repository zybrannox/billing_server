import os
from typing import Generator
from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
 
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        raise RuntimeError(f"{name} must be an integer")


# Pool sizing is tunable per deployment (a request holds one connection for
# its duration, so pool_size + max_overflow is the ceiling on concurrent DB
# work). pool_pre_ping drops connections the server closed while idle instead
# of failing the first request after a quiet period; pool_recycle keeps
# connections younger than typical proxy/firewall idle timeouts. SQLite
# (tests) uses its own pool and rejects these arguments.
_pool_options: dict = {}
if not DATABASE_URL.startswith("sqlite"):
    _pool_options = {
        "pool_size": _int_env("DB_POOL_SIZE", 10),
        "max_overflow": _int_env("DB_MAX_OVERFLOW", 10),
        "pool_timeout": _int_env("DB_POOL_TIMEOUT_SECONDS", 30),
        "pool_recycle": _int_env("DB_POOL_RECYCLE_SECONDS", 1800),
        "pool_pre_ping": True,
    }

engine = create_engine(DATABASE_URL, future=True, echo=False, **_pool_options)

from .slow_queries import install as _install_slow_query_log

_install_slow_query_log(engine)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
