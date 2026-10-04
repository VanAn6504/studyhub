"""Create a separate PostgreSQL test DB, migrate it, then run integration tests."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
config = dotenv_values(root / ".env")
base_url = os.environ.get("DATABASE_URL") or config.get("DATABASE_URL")
if not base_url:
    raise SystemExit("Generate .env with scripts/setup.ps1 first.")
base = make_url(base_url)
test = make_url(os.environ["TEST_DATABASE_URL"]) if os.environ.get("TEST_DATABASE_URL") else base.set(database=f"{base.database}_test")
if test.drivername != "postgresql+psycopg" or not (test.database or "").endswith("_test"):
    raise SystemExit("Only PostgreSQL database names ending in _test are allowed.")
# Compose publishes Postgres on IPv4 loopback. On Windows, libpq's initial
# IPv6 localhost attempt otherwise adds a timeout to each new connection.
if test.host == "localhost":
    test = test.set(host="127.0.0.1")
print(f"Preparing dedicated test database {test.database} at {test.host}:{test.port or 5432}.", flush=True)
admin = create_engine(
    test.set(database="postgres"), isolation_level="AUTOCOMMIT",
    connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    pool_timeout=10,
)
try:
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": test.database})
        if not exists:
            identifier = conn.dialect.identifier_preparer.quote(test.database)
            conn.execute(text(f"CREATE DATABASE {identifier}"))
finally:
    admin.dispose()
env = os.environ.copy()
env.update(TEST_DATABASE_URL=test.render_as_string(hide_password=False), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
print("Running backend integration tests against a dedicated PostgreSQL test database.", flush=True)
result = subprocess.run([sys.executable, "-m", "pytest", "-q", *sys.argv[1:]], cwd=root / "backend", env=env)
raise SystemExit(result.returncode)
