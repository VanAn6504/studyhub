"""Integration tests use a separate, explicitly named PostgreSQL test database."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL and a database name ending in _test")
    if parsed.host == "localhost":
        parsed = parsed.set(host="127.0.0.1")
        url = parsed.render_as_string(hide_password=False)
    os.environ.update(
        DATABASE_URL=url,
        JWT_SECRET=secrets.token_hex(32),
        ALLOWED_ORIGINS=ORIGIN,
        COOKIE_SECURE="false",
        AUTH_RATE_LIMIT="1000",
    )
    print("[database] Applying migrations to dedicated test database.", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND,
        env=os.environ.copy(), capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000 -c lock_timeout=5000"}, pool_timeout=10)
    print("[database] Migration complete.", flush=True)
    yield engine
    engine.dispose()


@pytest.fixture
def seeded(database):
    print("[seeded] Resetting dedicated test database.", flush=True)
    with database.begin() as conn:
        conn.execute(text("TRUNCATE TABLE users CASCADE"))
    teacher_password, student_password = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
    env = os.environ.copy()
    env.update(
        BOOTSTRAP_TEACHER_EMAIL="teacher@example.com",
        BOOTSTRAP_TEACHER_PASSWORD=teacher_password,
        BOOTSTRAP_TEACHER_DISPLAY_NAME="Giảng viên test",
        DEMO_STUDENT_EMAIL="student@example.com",
        DEMO_STUDENT_PASSWORD=student_password,
        DEMO_STUDENT_DISPLAY_NAME="Sinh viên test",
        COURSE_RUN_CODE="TEST_RUN",
        COURSE_RUN_START_DATE="2026-10-03",
        PYTHONIOENCODING="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "app.seed"], cwd=BACKEND,
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    print("[seeded] Foundation data ready.", flush=True)
    return {"teacher": teacher_password, "student": student_password, "env": env}


@pytest.fixture
def client(seeded):
    print("[client] Importing app and starting TestClient.", flush=True)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as value:
        print("[client] TestClient ready.", flush=True)
        yield value


@pytest.fixture
def teacher(client, seeded):
    response = client.post("/api/v1/auth/login", headers={"Origin": ORIGIN},
                           json={"email": "teacher@example.com", "password": seeded["teacher"]})
    assert response.status_code == 200, response.text
    return client, {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def student(client, seeded):
    response = client.post("/api/v1/auth/login", headers={"Origin": ORIGIN},
                           json={"email": "student@example.com", "password": seeded["student"]})
    assert response.status_code == 200, response.text
    return client, {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}
