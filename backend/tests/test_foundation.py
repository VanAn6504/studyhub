import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt

from sqlalchemy import text

from conftest import BACKEND, ORIGIN

PREFIX = "/api/v1"


def test_health_and_seed_idempotency(client, seeded, database):
    assert client.get(f"{PREFIX}/health").status_code == 200
    result = subprocess.run([sys.executable, "-m", "app.seed"], cwd=BACKEND,
                            env=seeded["env"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    with database.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM topics")) == 8
        assert conn.scalar(text("SELECT count(*) FROM courses")) == 1
        assert conn.scalar(text("SELECT count(*) FROM enrollments")) == 1


def test_registration_normalization_and_privilege_rejection(client):
    body = {"email": " New.Student@Example.com ", "password": "IndependentTest123!", "display_name": "Student"}
    denied = client.post(f"{PREFIX}/auth/register", headers={"Origin": ORIGIN}, json={**body, "role": "teacher"})
    assert denied.status_code == 422
    response = client.post(f"{PREFIX}/auth/register", headers={"Origin": ORIGIN}, json=body)
    assert response.status_code == 201
    assert response.json()["email"] == "new.student@example.com"
    assert response.json()["role"] == "student"
    assert set(response.json()) == {"id", "email", "display_name", "role"}
    assert client.post(f"{PREFIX}/auth/register", headers={"Origin": ORIGIN}, json=body).status_code == 409


def test_auth_origin_and_error_envelope(client):
    body = {"email": "student@example.com", "password": "incorrect"}
    for headers in ({}, {"Origin": "https://unexpected.example"}):
        response = client.post(f"{PREFIX}/auth/login", headers=headers, json=body)
        assert response.status_code == 403
        assert set(response.json()) == {"error", "request_id"}
    wrong = client.post(f"{PREFIX}/auth/login", headers={"Origin": ORIGIN}, json=body)
    unknown = client.post(f"{PREFIX}/auth/login", headers={"Origin": ORIGIN}, json={**body, "email": "unknown@example.com"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_logout_revokes_cookie_and_csrf_is_required(teacher):
    client, headers = teacher
    me = client.get(f"{PREFIX}/auth/me")
    assert me.status_code == 200 and me.json()["user"]["role"] == "teacher"
    old_cookie = client.cookies.get("studyhub_access")
    denied = client.post(f"{PREFIX}/auth/logout", headers={"Origin": ORIGIN})
    assert denied.status_code == 403
    assert client.get(f"{PREFIX}/auth/me").status_code == 200
    assert client.post(f"{PREFIX}/auth/logout", headers=headers).status_code == 204
    assert client.get(f"{PREFIX}/auth/me", headers={"Cookie": f"studyhub_access={old_cookie}"}).status_code == 401


def test_login_cookie_flags_and_inactive_user(client, seeded, database):
    response = client.post(f"{PREFIX}/auth/login", headers={"Origin": ORIGIN},
                           json={"email": "student@example.com", "password": seeded["student"]})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert set(response.json()) == {"user", "csrf_token"}
    with database.begin() as conn:
        conn.execute(text("UPDATE users SET is_active=false WHERE email='student@example.com'"))
    assert client.get(f"{PREFIX}/auth/me").status_code == 401
    assert client.post(f"{PREFIX}/auth/login", headers={"Origin": ORIGIN},
                       json={"email": "student@example.com", "password": seeded["student"]}).status_code == 401


def test_student_course_scope_and_empty_enrollment(student):
    client, headers = student
    assert client.get(f"{PREFIX}/courses").status_code == 403
    runs = client.get(f"{PREFIX}/course-runs").json()
    assert runs["total"] == 1
    run = runs["items"][0]
    topics = client.get(f"{PREFIX}/course-runs/{run['id']}/topics")
    assert topics.status_code == 200 and topics.json()["total"] == 8
    assert all(t["materials"] == [] and t["quiz"] is None for t in topics.json()["items"])
    assert client.get(f"{PREFIX}/courses/{run['course_id']}/topics").status_code == 403
    assert client.post(f"{PREFIX}/courses", headers=headers, json={"code": "FORBIDDEN", "title": "No"}).status_code == 403


def test_new_student_not_enrolled(client):
    body = {"email": "outsider@example.com", "password": "IndependentTest123!", "display_name": "Outsider"}
    assert client.post(f"{PREFIX}/auth/register", headers={"Origin": ORIGIN}, json=body).status_code == 201
    assert client.post(f"{PREFIX}/auth/login", headers={"Origin": ORIGIN},
                       json={"email": body["email"], "password": body["password"]}).status_code == 200
    assert client.get(f"{PREFIX}/course-runs").json()["items"] == []


def test_teacher_can_create_run_and_enroll_idempotently(teacher):
    client, headers = teacher
    course = client.get(f"{PREFIX}/courses").json()["items"][0]
    created = client.post(f"{PREFIX}/courses/{course['id']}/runs", headers=headers,
                          json={"code": "NEW_RUN", "course_run_start_date": "2026-10-03", "timezone": "Asia/Bangkok"})
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "draft" and run["data_origin"] == "real"
    assert client.patch(f"{PREFIX}/course-runs/{run['id']}", headers=headers, json={"status": "active"}).status_code == 200
    body = {"student_email": " STUDENT@EXAMPLE.COM "}
    first = client.post(f"{PREFIX}/course-runs/{run['id']}/enrollments", headers=headers, json=body)
    assert first.status_code == 201
    second = client.post(f"{PREFIX}/course-runs/{run['id']}/enrollments", headers=headers, json=body)
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    assert client.post(f"{PREFIX}/course-runs/{run['id']}/enrollments", headers=headers,
                       json={"student_email": "teacher@example.com"}).status_code == 404


def test_prerequisite_cycle_rejected_without_partial_write(teacher):
    client, headers = teacher
    course = client.get(f"{PREFIX}/courses").json()["items"][0]
    topics = client.get(f"{PREFIX}/courses/{course['id']}/topics").json()["items"]
    by_code = {t["code"]: t for t in topics}
    response = client.put(f"{PREFIX}/topics/{by_code['FL01']['id']}/prerequisites", headers=headers,
                          json={"prerequisite_topic_ids": [by_code["FL04"]["id"]]})
    assert response.status_code == 422
    after = client.get(f"{PREFIX}/courses/{course['id']}/topics").json()["items"]
    assert next(t for t in after if t["code"] == "FL01")["prerequisite_topic_ids"] == []


def test_resource_ownership_and_cross_course_prerequisite(teacher):
    client, headers = teacher
    course = client.get(f"{PREFIX}/courses").json()["items"][0]
    topics = client.get(f"{PREFIX}/courses/{course['id']}/topics").json()["items"]
    other = client.post(f"{PREFIX}/courses", headers=headers, json={"code": "OTHER", "title": "Other"}).json()
    topic = client.post(f"{PREFIX}/courses/{other['id']}/topics", headers=headers,
                        json={"code": "OTHER01", "title": "Other topic", "order_index": 1, "objectives": []}).json()
    assert client.put(f"{PREFIX}/topics/{topics[0]['id']}/prerequisites", headers=headers,
                      json={"prerequisite_topic_ids": [topic["id"]]}).status_code == 422


def test_other_teacher_cannot_read_or_modify_course(client, database):
    body = {"email": "other.teacher@example.com", "password": "IndependentTest123!", "display_name": "Other"}
    assert client.post(f"{PREFIX}/auth/register", headers={"Origin": ORIGIN}, json=body).status_code == 201
    with database.begin() as conn:
        course_id = str(conn.scalar(text("SELECT id FROM courses LIMIT 1")))
        conn.execute(text("UPDATE users SET role='teacher' WHERE email='other.teacher@example.com'"))
    login = client.post(f"{PREFIX}/auth/login", headers={"Origin": ORIGIN},
                        json={"email": body["email"], "password": body["password"]})
    headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
    assert client.get(f"{PREFIX}/courses").json()["items"] == []
    assert client.get(f"{PREFIX}/courses/{course_id}/topics").status_code == 404
    assert client.post(f"{PREFIX}/courses/{course_id}/runs", headers=headers,
                       json={"code": "NO_ACCESS", "course_run_start_date": "2026-10-03", "timezone": "Asia/Bangkok"}).status_code == 404


def test_concurrent_enrollment_keeps_one_row(teacher):
    client, headers = teacher
    course = client.get(f"{PREFIX}/courses").json()["items"][0]
    run = client.post(f"{PREFIX}/courses/{course['id']}/runs", headers=headers,
                      json={"code": "CONCURRENT", "course_run_start_date": "2026-10-03", "timezone": "Asia/Bangkok"}).json()
    def enroll(_):
        return client.post(f"{PREFIX}/course-runs/{run['id']}/enrollments", headers=headers,
                           json={"student_email": "student@example.com"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(enroll, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]


def test_bad_and_expired_tokens_are_unauthorized(teacher):
    from app.config import get_settings
    client, _ = teacher
    token = client.cookies.get("studyhub_access")
    payload = jwt.decode(token, options={"verify_signature": False})
    secret = get_settings().jwt_secret.get_secret_value()
    expired = {**payload, "iat": datetime.now(timezone.utc) - timedelta(hours=2),
               "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
    malformed_ids = {**payload, "sub": "invalid-uuid"}
    tokens = ["broken-token", jwt.encode(payload, "independent-test-signing-secret-32-bytes", algorithm="HS256"),
              jwt.encode(expired, secret, algorithm="HS256"), jwt.encode(malformed_ids, secret, algorithm="HS256")]
    for candidate in tokens:
        response = client.get(f"{PREFIX}/auth/me", headers={"Cookie": f"studyhub_access={candidate}"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_wrong_csrf_origin_and_changed_role(teacher, database):
    client, headers = teacher
    body = {"code": "DENIED", "title": "Denied"}
    for overridden in ({"X-CSRF-Token": "incorrect"}, {"Origin": "https://untrusted.example"}):
        response = client.post(f"{PREFIX}/courses", headers={**headers, **overridden}, json=body)
        assert response.status_code == 403
    with database.begin() as conn:
        conn.execute(text("UPDATE users SET role='student' WHERE email='teacher@example.com'"))
    assert client.get(f"{PREFIX}/courses").status_code == 403
    assert client.get(f"{PREFIX}/auth/me").json()["user"]["role"] == "student"


def test_run_topics_require_active_enrollment(client, database):
    with database.connect() as conn:
        run_id = str(conn.scalar(text("SELECT id FROM course_runs LIMIT 1")))
    body = {"email": "outsider@example.com", "password": "IndependentTest123!", "display_name": "Outsider"}
    assert client.post(f"{PREFIX}/auth/register", headers={"Origin": ORIGIN}, json=body).status_code == 201
    assert client.post(f"{PREFIX}/auth/login", headers={"Origin": ORIGIN},
                       json={"email": body["email"], "password": body["password"]}).status_code == 200
    assert client.get(f"{PREFIX}/course-runs/{run_id}/topics").status_code == 404


def test_inactive_enrollment_loses_run_access(student, database):
    client, _ = student
    run_id = client.get(f"{PREFIX}/course-runs").json()["items"][0]["id"]
    with database.begin() as conn:
        conn.execute(text("UPDATE enrollments SET status='inactive' WHERE course_run_id=:run"), {"run": run_id})
    assert client.get(f"{PREFIX}/course-runs/{run_id}/topics").status_code == 404
    assert client.get(f"{PREFIX}/course-runs").json()["items"] == []
