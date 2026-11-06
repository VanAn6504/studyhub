import hashlib
import json
import platform
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import joblib
import numpy as np
import pytest
import sklearn
import xgboost
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from conftest import ORIGIN
from test_learning import P, begin, event, login, make_quiz, send_events, setup_content


@pytest.fixture(autouse=True)
def isolated_files(tmp_path, client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'pdf_storage_path', tmp_path / 'pdf')
    monkeypatch.setattr(get_settings(), 'model_artifact_path', tmp_path / 'absent')


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.features import FEATURES_B
    x = np.array([[0, 0, 43, 0, np.nan, 0], [3, 12, 0, 1, 40, 1],
                  [12, 70, 1, 2, 95, 1], [18, 85, 0, 2, 90, 1]], dtype=float)
    model = Pipeline([('imputer', SimpleImputer(strategy='median')), ('classifier', RandomForestClassifier(n_estimators=5, random_state=7))])
    model.fit(x, [1, 1, 0, 0])
    directory = tmp_path / 'artifact'
    directory.mkdir()
    joblib.dump({'model': model, 'background': x}, directory / 'model.joblib')
    manifest = dict(artifact_version=1, code='test_' + uuid4().hex,
        artifact_sha256=hashlib.sha256((directory / 'model.joblib').read_bytes()).hexdigest(),
        feature_set='B', feature_schema_version='features_v1', feature_order=FEATURES_B,
        cutoff_day=42, class_mapping={'0': 'Pass/Distinction', '1': 'Fail'}, threshold=0.4,
        threshold_source='validation_max_fail_f1', calibration_status='uncalibrated', output_space='raw_probability',
        preprocessing={'strategy': 'train_only_median', 'statistics': model.named_steps['imputer'].statistics_.tolist()},
        libraries={'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__, 'xgboost': xgboost.__version__, 'joblib': joblib.__version__})
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.setattr(get_settings(), 'model_artifact_path', directory)
    return directory


def complete(client, headers, run, topic, quiz, correct=3):
    attempt = begin(client, headers, run, topic, quiz).json()
    answers = [{'quiz_version_item_id': item['quiz_version_item_id'], 'selected_option': 'B' if i < correct else 'A'} for i, item in enumerate(attempt['items'])]
    saved = client.put(f"{P}/attempts/{attempt['id']}/answers", headers=headers, json={'expected_revision': 0, 'answers': answers})
    assert saved.status_code == 200, saved.text
    response = client.post(f"{P}/attempts/{attempt['id']}/submit", headers=headers, json={'expected_revision': 1})
    assert response.status_code == 200, response.text
    return response.json()


def test_path_current_mastery_prerequisites_revisions_and_retry(client, seeded, database):
    headers, run, topics, document = setup_content(client, seeded)
    third, fourth = topics[2:4]
    q3 = make_quiz(client, headers, third, document['versions'][0]['id'])
    q4 = make_quiz(client, headers, fourth, document['versions'][0]['id'])
    headers = login(client, seeded, 'student')
    url = f"{P}/course-runs/{run['id']}/learning-path"
    first = client.get(url).json()
    assert [s['topic_code'] for s in first['steps']] == ['FL03', 'FL04']
    assert all(s['state'] == 'not_assessed' and s['score_percent'] is None for s in first['steps'])
    assert first['warnings'] and len(first['unavailable_topics']) == 6
    assert client.get(url).json()['revision'] == first['revision']
    low = complete(client, headers, run, fourth, q4, correct=1)
    weak = client.get(url).json()
    assert [s['topic_code'] for s in weak['steps']] == ['FL03', 'FL04']
    assert weak['steps'][0]['reason'] == 'unassessed_prerequisite'
    assert weak['steps'][1]['state'] == 'weak'
    assert low['path_revision'] == weak['revision'] == first['revision'] + 1
    assert datetime.fromisoformat(weak['generated_at']) >= datetime.fromisoformat(low['graded_at'])
    retry = client.post(f"{P}/attempts/{low['id']}/submit", headers=headers, json={'expected_revision': 0}).json()
    assert retry['path_revision'] == low['path_revision']
    passed = complete(client, headers, run, fourth, q4)
    latest = client.get(url).json()
    assert [s['topic_code'] for s in latest['steps']] == ['FL03']
    assert latest['revision'] == passed['path_revision'] == weak['revision'] + 1
    with database.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM learning_paths')) == 3
    teacher = login(client, seeded, 'teacher')
    make_quiz(client, teacher, fourth, document['versions'][0]['id'])
    report = client.get(f"{P}/course-runs/{run['id']}/report").json()['items'][0]['learning_path']
    state = next(s for s in report['topic_states'] if s['topic_code'] == 'FL04')
    assert state['state'] == 'not_assessed' and state['reason'] == 'content_changed'
    assert state['score_percent'] is None and report['revision'] == latest['revision'] + 1


def test_path_get_concurrency_and_acl(client, seeded, database):
    headers, run, topics, document = setup_content(client, seeded)
    make_quiz(client, headers, topics[0], document['versions'][0]['id'])
    login(client, seeded, 'student')
    url = f"{P}/course-runs/{run['id']}/learning-path"
    cookie = dict(client.cookies)
    from fastapi.testclient import TestClient
    from app.main import app
    def read(_):
        with TestClient(app) as other:
            other.cookies.update(cookie)
            response = other.get(url)
            assert response.status_code == 200, response.text
            return response.json()['revision']
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(read, range(2))) == [1, 1]
    with database.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM learning_paths')) == 1
    assert client.get(f'{P}/course-runs/{uuid4()}/learning-path').status_code == 404
    login(client, seeded, 'teacher')
    assert client.get(url).status_code == 403
    client.cookies.clear()
    assert client.get(url).status_code == 401


def test_features_boundary_first_attempt_received_time_and_origin(client, seeded, database):
    from app.features import cutoff_bounds, studyhub_features
    from app.learning_models import LearningEvent, QuizAttempt
    from app.models import CourseRun, Enrollment
    headers, run, topics, document = setup_content(client, seeded)
    quizzes = [make_quiz(client, headers, topic, document['versions'][0]['id']) for topic in topics[:2]]
    headers = login(client, seeded, 'student')
    attempts = [complete(client, headers, run, topics[0], quizzes[0], 1), complete(client, headers, run, topics[0], quizzes[0], 3), complete(client, headers, run, topics[1], quizzes[1], 2)]
    with Session(database) as db:
        actual_run = db.get(CourseRun, UUID(run['id']))
        enrollment = db.scalar(select(Enrollment).where(Enrollment.course_run_id == actual_run.id))
        lower, upper = cutoff_bounds(actual_run.course_run_start_date, actual_run.timezone)
        for attempt, day in zip(attempts, [10, 11, 12]):
            db.get(QuizAttempt, UUID(attempt['id'])).graded_at = lower + timedelta(days=day, hours=1)
        # Day42 included; late arrival, wrong origin, doc_open and exact day43 excluded.
        for day, kind, origin, late in [(0,'page_view','real',False), (2,'page_view','real',False),
                (42,'page_view','real',False), (43,'page_view','real',False), (1,'page_view','synthetic',False),
                (3,'page_view','real',True), (4,'document_open','real',False)]:
            at = lower + timedelta(days=day, hours=0 if day == 43 else 1)
            db.add(LearningEvent(enrollment_id=enrollment.id, client_event_id=uuid4(), viewer_session_id=uuid4(),
                type=kind, document_version_id=UUID(document['versions'][0]['id']), pdf_page=1 if kind == 'page_view' else None,
                occurred_at=at, received_at=upper if late else at, data_origin=origin))
        db.flush()
        features = studyhub_features(db, actual_run, enrollment)
        assert features == dict(active_days=3, material_interactions=3, days_since_last_activity=0,
            assessment_count=2, mean_assessment_score=50, has_assessment=1)
        db.get(QuizAttempt, UUID(attempts[2]['id'])).graded_at = upper
        db.flush()
        assert studyhub_features(db, actual_run, enrollment)['assessment_count'] == 1
        db.rollback()
    # Calendar midnight in a DST zone is not a fixed 43*24 hour duration.
    lo, hi = cutoff_bounds(date(2026, 3, 1), 'America/New_York')
    assert (hi - lo).total_seconds() == (43 * 24 - 1) * 3600


def mature(database, run_id):
    with database.begin() as conn:
        conn.execute(text("UPDATE course_runs SET course_run_start_date='2020-01-01' WHERE id=:id"), {'id': run_id})


def test_class_deadline_version_scope_completion_and_removal(client, seeded, database, monkeypatch):
    from app import activity, quizzes
    from app.models import CourseRun

    teacher, run, topics, doc = setup_content(client, seeded)
    quiz = make_quiz(client, teacher, topics[0], doc['versions'][0]['id'])
    route = f"{P}/teaching/runs/{run['id']}/quiz-schedule"
    set_url = f"{route}/{quiz['id']}"
    assert client.get(route).json()['items'][0]['due_at'] is None
    assert client.put(set_url, headers={'Origin': ORIGIN}, json={'due_local': None}).status_code == 403
    assert client.put(set_url, headers=teacher, json={'due_local': '2026-11-04T12:00+07:00'}).status_code == 422
    saved = client.put(set_url, headers=teacher, json={'due_local': '2026-11-04T12:00'})
    assert saved.status_code == 200, saved.text
    assert saved.json()['due_local'] == '2026-11-04T12:00'
    other_run = client.post(f"{P}/courses/{run['course_id']}/runs", headers=teacher, json={
        'code': 'OTHER_DEADLINE', 'course_run_start_date': '2026-11-01', 'timezone': run['timezone']}).json()
    assert client.get(f"{P}/teaching/runs/{other_run['id']}/quiz-schedule").json()['items'][0]['due_at'] is None
    start = datetime.fromisoformat(saved.json()['due_at'])
    with Session(database) as db:
        db.get(CourseRun, UUID(run['id'])).course_run_start_date = date(2026, 11, 1)
        db.commit()
    now = start - timedelta(seconds=1)
    monkeypatch.setattr(activity, 'utcnow', lambda: now)
    monkeypatch.setattr(quizzes, 'utcnow', lambda: now)
    headers = login(client, seeded, 'student')
    assert client.get(route).status_code == 403
    activity_url = f"{P}/course-runs/{run['id']}/learning-activity"
    def scheduled():
        response = client.get(activity_url)
        assert response.status_code == 200, response.text
        return response.json()['schedule']
    assert scheduled()[0]['status'] == 'due_soon'
    complete(client, headers, run, topics[0], quiz)
    assert scheduled()[0]['status'] == 'submitted_on_time'
    teacher = login(client, seeded, 'teacher')
    next_quiz = make_quiz(client, teacher, topics[0], doc['versions'][0]['id'])
    assert client.put(set_url, headers=teacher, json={'due_local': None}).status_code == 409
    next_url = f"{route}/{next_quiz['id']}"
    assert client.put(next_url, headers=teacher, json={'due_local': '2026-11-04T12:00'}).status_code == 200
    headers = login(client, seeded, 'student')
    now = start + timedelta(seconds=1)
    rows = {item['quiz_version_id']: item for item in scheduled()}
    assert rows[quiz['id']]['status'] == 'submitted_on_time' and not rows[quiz['id']]['current']
    assert rows[next_quiz['id']]['status'] == 'overdue'
    complete(client, headers, run, topics[0], next_quiz)
    rows = {item['quiz_version_id']: item for item in scheduled()}
    assert rows[next_quiz['id']]['status'] == 'submitted_late' and rows[next_quiz['id']]['graded']
    teacher = login(client, seeded, 'teacher')
    assert client.put(next_url, headers=teacher, json={'due_local': None}).status_code == 200
    login(client, seeded, 'student')
    assert [item['quiz_version_id'] for item in scheduled()] == [quiz['id']]


def test_daily_forecast_matches_snapshot_boundaries_and_caches(client, seeded, database, tmp_path, monkeypatch):
    from app import activity, engagement_predictions
    from app.config import get_settings
    from app.engagement_features import FEATURES, SCHEMA
    from app.learning_models import DocumentVersion, LearningEvent
    from app.models import CourseRun, Enrollment
    from test_learning import pdf_bytes

    teacher, run, _, doc = setup_content(client, seeded)
    pdf = doc['versions'][0]['id']
    response = client.post(f"{P}/documents/{doc['id']}/versions", headers=teacher,
                           files={'file': ('next.pdf', pdf_bytes(), 'application/pdf')})
    assert response.status_code == 201, response.text
    second_pdf = response.json()['id']
    headers = login(client, seeded, 'student')
    start = datetime(2026, 3, 7, 5, tzinfo=timezone.utc)  # Midnight New York before DST.
    now = start
    monkeypatch.setattr(engagement_predictions, 'utcnow', lambda: now)
    monkeypatch.setattr(activity, 'utcnow', lambda: now)
    directory = tmp_path / 'daily'
    monkeypatch.setattr(get_settings(), 'engagement_artifact_path', directory)
    url = f"{P}/course-runs/{run['id']}"
    with Session(database) as db:
        actual = db.get(CourseRun, UUID(run['id']))
        actual.course_run_start_date, actual.timezone = start.date(), 'America/New_York'
        enrollment = db.scalar(select(Enrollment).where(Enrollment.course_run_id == actual.id))
        assert second_pdf != pdf
        assert db.get(DocumentVersion, UUID(second_pdf)).learning_document_id == UUID(doc['id'])
        for when, version, origin in [(start, pdf, 'real'), (start + timedelta(hours=2), second_pdf, 'real'),
                                      (start + timedelta(hours=24), second_pdf, 'real'),
                                      (start + timedelta(hours=26), second_pdf, 'synthetic')]:
            db.add(LearningEvent(enrollment_id=enrollment.id, client_event_id=uuid4(), viewer_session_id=uuid4(),
                type='page_view', document_version_id=UUID(version), pdf_page=1,
                occurred_at=when, received_at=when, data_origin=origin))
        db.commit()
    assert client.post(url + '/engagement-forecast', headers=headers).json()['status'] == 'not_ready'
    now = start + timedelta(hours=24)
    assert client.post(url + '/engagement-forecast', headers=headers).json()['status'] == 'model_unavailable'
    activity_now = client.get(url + '/learning-activity').json()
    assert (activity_now['active_days_7'], activity_now['page_views_7'], activity_now['documents_7']) == (2, 3, 1)
    assert activity_now['last_read']['document_version_id'] == second_pdf
    x = np.array([[1, 0, 0, 1, 0], [1, 1, 1, 0, 1], [2, 0, 0, 2, 0], [2, 2, 2, 0, 1]])
    model = RandomForestClassifier(n_estimators=3, random_state=7).fit(x, [1, 0, 1, 0])
    directory.mkdir()
    joblib.dump({'model': model, 'background': x}, directory / 'model.joblib')
    manifest = dict(artifact_version=1, code='daily_fixture',
        artifact_sha256=hashlib.sha256((directory / 'model.joblib').read_bytes()).hexdigest(),
        feature_set='activity_daily', feature_schema_version=SCHEMA, feature_order=FEATURES,
        supported_ranges=[[0, 6]], class_mapping={'0': 'Pass/Distinction', '1': 'Fail'}, threshold=0.4,
        threshold_source='validation_max_fail_f1', calibration_status='uncalibrated', output_space='raw_probability',
        libraries={'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__,
                   'xgboost': xgboost.__version__, 'joblib': joblib.__version__})
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert client.get(url + '/engagement-forecast').json()['status'] == 'not_computed'
    assert client.post(url + '/engagement-forecast', headers={'Origin': ORIGIN}).status_code == 403
    first = client.post(url + '/engagement-forecast', headers=headers).json()
    assert first['status'] == 'ok'
    assert first['feature_snapshot'] == dict(elapsed_days=1, active_days=1, active_days_7=1,
        days_since_last_activity=0, distinct_resources=1)
    assert client.post(url + '/engagement-forecast', headers=headers).json()['id'] == first['id']
    now = start + timedelta(hours=47)
    second = client.post(url + '/engagement-forecast', headers=headers).json()
    assert second['id'] != first['id'] and second['feature_snapshot']['active_days'] == 2
    assert datetime.fromisoformat(second['cutoff_end_at']) == now
    now = start + timedelta(days=9)
    assert client.get(url + '/engagement-forecast').json()['status'] == 'outside_range'
    now = start + timedelta(days=44)
    outside = client.post(url + '/engagement-forecast', headers=headers).json()
    assert outside['status'] == 'outside_range' and outside['risk_score'] is None
    client.cookies.clear()
    assert client.get(url + '/engagement-forecast').status_code == 401
    with database.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM learning_events')) == 4
        assert conn.scalar(text('SELECT count(*) FROM predictions')) == 2


def test_current_learning_activity_uses_local_days_and_read_only(client, seeded, database, monkeypatch):
    from app import activity, predictions
    from app.learning_models import LearningEvent
    from app.models import CourseRun, Enrollment

    _, run, _, document = setup_content(client, seeded)
    login(client, seeded, 'student')
    start = datetime(2026, 3, 1, 5, tzinfo=timezone.utc)  # Midnight in New York.
    now = start - timedelta(seconds=1)
    monkeypatch.setattr(activity, 'utcnow', lambda: now)
    monkeypatch.setattr(predictions, 'utcnow', lambda: now)
    url = f"{P}/course-runs/{run['id']}"
    with Session(database) as db:
        actual = db.get(CourseRun, UUID(run['id']))
        actual.course_run_start_date = start.date()
        actual.timezone = 'America/New_York'
        db.commit()
    future = client.get(url + '/learning-activity').json()
    assert not future['started'] and future['completed_days'] == future['page_views'] == 0
    assert datetime.fromisoformat(future['starts_at']) == start
    now = start + timedelta(days=10)
    empty = client.get(url + '/learning-activity').json()
    assert empty['started'] and empty['completed_days'] == 10 and empty['active_days'] == empty['page_views'] == 0

    with Session(database) as db:
        enrollment = db.scalar(select(Enrollment).where(Enrollment.course_run_id == UUID(run['id'])))
        for offset, kind, origin, received_offset in [
            (-1, 'page_view', 'real', -1), (1, 'page_view', 'real', 1),
            (2, 'page_view', 'real', 2), (24, 'page_view', 'real', 24),
            (25, 'document_open', 'real', 25), (26, 'page_view', 'synthetic', 26),
            (27, 'page_view', 'real', 241), (241, 'page_view', 'real', 241),
            (24 * 45, 'page_view', 'real', 24 * 45),
        ]:
            db.add(LearningEvent(enrollment_id=enrollment.id, client_event_id=uuid4(), viewer_session_id=uuid4(),
                type=kind, document_version_id=UUID(document['versions'][0]['id']), pdf_page=1 if kind == 'page_view' else None,
                occurred_at=start + timedelta(hours=offset), received_at=start + timedelta(hours=received_offset),
                data_origin=origin))
        db.commit()
    current = client.get(url + '/learning-activity').json()
    assert (current['active_days'], current['page_views'], current['completed_days'], current['window_days']) == (2, 3, 10, 43)
    prediction = client.get(url + '/prediction').json()
    assert prediction['status'] == 'not_ready' and prediction['risk_score'] is None
    cutoff = datetime.fromisoformat(current['cutoff_end_at'])
    assert datetime.fromisoformat(prediction['cutoff_end_at']) == cutoff == start + timedelta(hours=43 * 24 - 1)
    now = cutoff - timedelta(seconds=1)
    assert client.get(url + '/learning-activity').json()['completed_days'] == 42
    now = cutoff
    assert client.get(url + '/learning-activity').json()['completed_days'] == 43
    assert client.get(url + '/prediction').json()['status'] == 'not_computed'
    now = start + timedelta(days=46)
    later = client.get(url + '/learning-activity').json()
    assert (later['page_views'], later['completed_days']) == (6, 43)
    with database.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM learning_events')) == 9
        assert conn.scalar(text('SELECT count(*) FROM predictions')) == 0


def test_prediction_states_missing_artifact_and_schema(client, seeded, database, artifact):
    headers = login(client, seeded, 'student')
    run = client.get(f'{P}/course-runs').json()['items'][0]
    url = f"{P}/course-runs/{run['id']}/predictions"
    assert client.post(url, headers=headers, json={'features': [1]}).status_code == 422
    assert client.post(url, headers={'Origin': ORIGIN}, json={}).status_code == 403
    assert client.post(url, headers=headers).json()['status'] == 'not_ready'
    mature(database, run['id'])
    assert client.get(url[:-1]).json()['status'] == 'not_computed'
    first = client.post(url, headers=headers).json()
    assert first['status'] == 'insufficient_data' and first['risk_score'] is None
    assert first['feature_snapshot']['mean_assessment_score'] is None
    assert first['feature_snapshot']['days_since_last_activity'] == 43
    assert client.post(url, headers=headers).json()['id'] == first['id']
    manifest = json.loads((artifact / 'manifest.json').read_text())
    manifest['cutoff_day'] = 28
    (artifact / 'manifest.json').write_text(json.dumps(manifest))
    unavailable = client.post(url, headers=headers)
    assert unavailable.status_code == 503 and unavailable.json()['error']['code'] == 'MODEL_UNAVAILABLE'
    login(client, seeded, 'teacher')
    assert client.patch(f"{P}/course-runs/{run['id']}", headers=login(client, seeded, 'teacher'),
        json={'course_run_start_date': '2021-01-01'}).status_code == 409


def test_prediction_success_shap_cache_concurrency_and_acl(client, seeded, database, artifact):
    from app.features import cutoff_bounds
    from app.learning_models import LearningEvent
    from app.models import CourseRun, Enrollment
    headers, run, _, document = setup_content(client, seeded)
    mature(database, run['id'])
    with Session(database) as db:
        actual_run = db.get(CourseRun, UUID(run['id']))
        enrollment = db.scalar(select(Enrollment).where(Enrollment.course_run_id == actual_run.id))
        lower, _ = cutoff_bounds(actual_run.course_run_start_date, actual_run.timezone)
        db.add(LearningEvent(enrollment_id=enrollment.id, client_event_id=uuid4(), viewer_session_id=uuid4(),
            type='page_view', document_version_id=UUID(document['versions'][0]['id']), pdf_page=1,
            occurred_at=lower + timedelta(days=2), received_at=lower + timedelta(days=2), data_origin='real'))
        db.commit()
    headers = login(client, seeded, 'student')
    cookie = dict(client.cookies)
    url = f"{P}/course-runs/{run['id']}/predictions"
    from fastapi.testclient import TestClient
    from app.main import app
    def compute(_):
        with TestClient(app) as other:
            other.cookies.update(cookie)
            response = other.post(url, headers=headers, json={})
            assert response.status_code == 200, response.text
            return response.json()
    with ThreadPoolExecutor(max_workers=2) as executor:
        one, two = executor.map(compute, range(2))
    assert one['id'] == two['id'] and one['status'] == 'ok'
    assert one['transport_status'] == 'unvalidated' and one['calibration_status'] == 'uncalibrated'
    explanation = one['explanation']
    assert explanation['base_value'] + sum(c['contribution'] for c in explanation['contributions']) == pytest.approx(one['risk_score'])
    assert client.get(url[:-1]).json()['id'] == one['id']
    assert client.post(f'{P}/course-runs/{uuid4()}/predictions', headers=headers).status_code == 404
    login(client, seeded, 'teacher')
    assert client.post(url, headers=login(client, seeded, 'teacher')).status_code == 403
    client.cookies.clear()
    assert client.get(url[:-1]).status_code == 401
    (artifact / 'model.joblib').write_bytes(b'corrupt artifact')
    headers = login(client, seeded, 'student')
    assert client.post(url, headers=headers).status_code == 503


def test_synthetic_read_only_prediction_provenance(client, seeded, database, artifact):
    headers, run, topics, document = setup_content(client, seeded)
    quiz = make_quiz(client, headers, topics[0], document['versions'][0]['id'])
    mature(database, run['id'])
    with database.begin() as conn:
        conn.execute(text("UPDATE course_runs SET data_origin='synthetic' WHERE id=:id"), {'id': run['id']})
    headers = login(client, seeded, 'student')
    assert send_events(client, headers, run, [event(document['versions'][0]['id'])]).status_code == 409
    assert begin(client, headers, run, topics[0], quiz).status_code == 409
    assert client.get(f"{P}/course-runs/{run['id']}/learning-path").json()['data_origin'] == 'synthetic'
    result = client.post(f"{P}/course-runs/{run['id']}/predictions", headers=headers).json()
    assert result['status'] == 'insufficient_data' and result['data_origin'] == 'synthetic'


def test_demo_cli_idempotence_and_real_timeline_preserved(client, seeded, database):
    from app.seed_prediction_demo import seed_demo
    from app.models import CourseRun
    headers, run, topics, document = setup_content(client, seeded)
    headers = login(client, seeded, 'student')
    quiz_headers = login(client, seeded, 'teacher')
    quiz = make_quiz(client, quiz_headers, topics[0], document['versions'][0]['id'])
    headers = login(client, seeded, 'student')
    complete(client, headers, run, topics[0], quiz)
    send_events(client, headers, run, [event(document['versions'][0]['id'])])
    with database.connect() as conn:
        before = conn.execute(text('SELECT course_run_start_date, timezone FROM course_runs WHERE id=:id'), {'id': run['id']}).one()
    seed_demo('MOBILE_MULTIPLATFORM', 'student@example.com')
    seed_demo('MOBILE_MULTIPLATFORM', 'student@example.com')
    with database.connect() as conn:
        assert conn.execute(text('SELECT course_run_start_date, timezone FROM course_runs WHERE id=:id'), {'id': run['id']}).one() == before
        assert conn.scalar(text("SELECT count(*) FROM learning_events WHERE data_origin='synthetic'")) == 3
        assert conn.scalar(text("SELECT count(*) FROM learning_events WHERE data_origin='real'")) == 1
        assert conn.scalar(text("SELECT count(*) FROM quiz_attempts")) == 1
    runs = client.get(f'{P}/course-runs').json()['items']
    demo = next(r for r in runs if r['code'] == 'ML_DEMO_42')
    assert len(runs) == 2 and demo['data_origin'] == 'synthetic' and demo['status'] == 'closed'
    real_url = f"{P}/course-runs/{run['id']}/learning-activity"
    demo_url = f"{P}/course-runs/{demo['id']}/learning-activity"
    real_activity = client.get(real_url).json()
    demo_activity = client.get(demo_url).json()
    assert real_activity['page_views'] == 1 and real_activity['linked_run']['id'] == demo['id']
    assert demo_activity['page_views'] == 3 and demo_activity['linked_run']['id'] == run['id']
    with database.begin() as conn:
        conn.execute(text("UPDATE enrollments SET status='inactive' WHERE course_run_id=:id"), {'id': demo['id']})
    assert client.get(real_url).json()['linked_run'] is None
    assert client.get(demo_url).status_code == 404
    with pytest.raises(ValueError, match='inactive'):
        seed_demo('MOBILE_MULTIPLATFORM', 'student@example.com')


def test_prediction_missing_model_and_other_student_access(client, seeded, database):
    headers, run, _, _ = setup_content(client, seeded)
    mature(database, run['id'])
    headers = login(client, seeded, 'student')
    url = f"{P}/course-runs/{run['id']}"
    unavailable = client.post(url + '/predictions', headers=headers)
    assert unavailable.status_code == 503 and unavailable.json()['error']['details']['status'] == 'model_unavailable'
    client.cookies.clear()
    email, password = 'outsider@example.com', uuid4().hex
    assert client.post(f'{P}/auth/register', headers={'Origin': ORIGIN}, json={
        'email': email, 'password': password, 'display_name': 'Outside'}).status_code == 201
    session = client.post(f'{P}/auth/login', headers={'Origin': ORIGIN}, json={'email': email, 'password': password}).json()
    outsider = {'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']}
    assert client.get(url + '/learning-path').status_code == 404
    assert client.get(url + '/learning-activity').status_code == 404
    assert client.get(url + '/engagement-forecast').status_code == 404
    assert client.post(url + '/engagement-forecast', headers=outsider).status_code == 404
    assert client.get(url + '/prediction').status_code == 404
    assert client.post(url + '/predictions', headers=outsider).status_code == 404


def test_path_material_publication_and_prerequisite_change(client, seeded):
    teacher, run, topics, document = setup_content(client, seeded)
    topic = topics[3]
    make_quiz(client, teacher, topic, document['versions'][0]['id'])
    student = login(client, seeded, 'student')
    url = f"{P}/course-runs/{run['id']}/learning-path"
    original = client.get(url).json()
    assert original['steps'][0]['materials'] == []
    teacher = login(client, seeded, 'teacher')
    assert client.put(f"{P}/topics/{topic['id']}/materials", headers=teacher, json={'items': [
        {'document_version_id': document['versions'][0]['id'], 'page_start': 2, 'page_end': 3, 'order_index': 1}]}).status_code == 200
    login(client, seeded, 'student')
    mapped = client.get(url).json()
    assert mapped['revision'] == original['revision'] + 1 and mapped['steps'][0]['materials'][0]['page_start'] == 2
    teacher = login(client, seeded, 'teacher')
    assert client.put(f"{P}/topics/{topic['id']}/prerequisites", headers=teacher,
        json={'prerequisite_topic_ids': [topics[1]['id']]}).status_code == 200
    login(client, seeded, 'student')
    edge = client.get(url).json()
    assert edge['revision'] == mapped['revision'] + 1 and edge['warnings'] == [{'topic_id': topics[1]['id'], 'reason': 'prerequisite_unavailable'}]
    teacher = login(client, seeded, 'teacher')
    assert client.patch(f"{P}/documents/{document['id']}", headers=teacher, json={'status': 'archived'}).status_code == 200
    login(client, seeded, 'student')
    archived = client.get(url).json()
    assert archived['revision'] == edge['revision'] + 1 and archived['steps'][0]['materials'] == []


def test_exact_shap_known_additive_model(client):
    from app.model_runtime import predict_explain
    class AdditiveOracle:
        def predict_proba(self, x):
            probability = 0.2 + 0.1 * x[:, 0] + 0.01 * x[:, 1]
            return np.column_stack([1 - probability, probability])
    score, explanation = predict_explain(AdditiveOracle(), np.array([[0, 0], [1, 1]], dtype=float), {'a': 2, 'b': 3}, ['a', 'b'])
    contributions = {c['feature']: c['contribution'] for c in explanation['contributions']}
    assert score == pytest.approx(0.43) and explanation['base_value'] == pytest.approx(0.255)
    assert contributions == pytest.approx({'a': 0.15, 'b': 0.025})


def test_concurrent_submit_one_path_and_failed_snapshot_rolls_back_grade(client, seeded, database, monkeypatch):
    from app import paths
    teacher, run, topics, document = setup_content(client, seeded)
    quiz = make_quiz(client, teacher, topics[0], document['versions'][0]['id'])
    headers = login(client, seeded, 'student')
    attempt = begin(client, headers, run, topics[0], quiz).json()
    url = f"{P}/attempts/{attempt['id']}/submit"
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: client.post(url, headers=headers, json={'expected_revision': 0}), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()['path_revision'] == 1
    pending = begin(client, headers, run, topics[0], quiz).json()
    original = paths.ensure_path
    def fail_snapshot(*args):
        original(*args)
        raise RuntimeError('Injected snapshot failure')
    monkeypatch.setattr(paths, 'ensure_path', fail_snapshot)
    with pytest.raises(RuntimeError, match='Injected snapshot failure'):
        client.post(f"{P}/attempts/{pending['id']}/submit", headers=headers, json={'expected_revision': 0})
    with database.connect() as conn:
        assert conn.scalar(text('SELECT status FROM quiz_attempts WHERE id=:id'), {'id': pending['id']}) == 'in_progress'
        assert conn.scalar(text('SELECT count(*) FROM learning_paths')) == 1
