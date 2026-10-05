import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from sqlalchemy import text

from conftest import ORIGIN

P = '/api/v1'


def pdf_bytes(pages=3, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=400, height=500)
    if encrypted:
        writer.encrypt('test-only-password')
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def private_pdf_storage(tmp_path, client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'pdf_storage_path', tmp_path / 'private-pdfs')


def login(client, seeded, role):
    client.cookies.clear()
    response = client.post(f'{P}/auth/login', headers={'Origin': ORIGIN}, json={'email': f'{role}@example.com', 'password': seeded[role]})
    assert response.status_code == 200, response.text
    return {'Origin': ORIGIN, 'X-CSRF-Token': response.json()['csrf_token']}


def setup_content(client, seeded, published=True):
    headers = login(client, seeded, 'teacher')
    run = client.get(f'{P}/course-runs').json()['items'][0]
    topics = client.get(f"{P}/courses/{run['course_id']}/topics").json()['items']
    response = client.post(f"{P}/courses/{run['course_id']}/documents", headers=headers,
                           data={'code': 'TESTPDF', 'title': 'Test PDF'}, files={'file': ('test.pdf', pdf_bytes(), 'application/pdf')})
    assert response.status_code == 201, response.text
    document = response.json()
    if published:
        assert client.patch(f"{P}/documents/{document['id']}", headers=headers, json={'status': 'published'}).status_code == 200
    return headers, run, topics, document


def make_quiz(client, headers, topic, version_id, publish=True):
    ids = []
    for index in range(3):
        response = client.post(f"{P}/topics/{topic['id']}/questions", headers=headers, json={
            'code': f'Q{uuid4().hex[:12]}', 'stem': f'Question {index}', 'options': {'A': 'first', 'B': 'second', 'C': 'third', 'D': 'fourth'},
            'correct_option': 'B', 'explanation': 'Explanation', 'sources': [{'document_version_id': version_id, 'pdf_page': index + 1}],
        })
        assert response.status_code == 201, response.text
        ids.append(response.json()['id'])
    response = client.post(f"{P}/topics/{topic['id']}/quiz-versions", headers=headers, json={'question_version_ids': ids})
    assert response.status_code == 201, response.text
    quiz = response.json()
    if publish:
        assert client.post(f"{P}/quiz-versions/{quiz['id']}/publish", headers=headers).status_code == 200
    return quiz


def begin(client, headers, run, topic, quiz, key=None):
    return client.post(f"{P}/course-runs/{run['id']}/topics/{topic['id']}/attempts", headers=headers,
                       json={'published_quiz_version_id': quiz['id'], 'request_key': key or str(uuid4())})


def event(version_id, **overrides):
    return {'client_event_id': str(uuid4()), 'viewer_session_id': str(uuid4()), 'type': 'page_view', 'document_version_id': version_id, 'pdf_page': 1, **overrides}


def send_events(client, headers, run, events):
    return client.post(f"{P}/course-runs/{run['id']}/events", headers=headers, json={'schema_version': 'learning_event_v1', 'events': events})


def test_pdf_publication_private_ranges_versions_and_mapping(client, seeded):
    headers, run, topics, document = setup_content(client, seeded, published=False)
    version = document['versions'][0]
    student = login(client, seeded, 'student')
    url = f"{P}/course-runs/{run['id']}/document-versions/{version['id']}/content"
    assert client.get(url).status_code == 404
    assert client.get(f"{P}/course-runs/{run['id']}/documents").json()['total'] == 0
    headers = login(client, seeded, 'teacher')
    assert client.patch(f"{P}/documents/{document['id']}", headers=headers, json={'status': 'published'}).status_code == 200
    mapping = {'items': [{'document_version_id': version['id'], 'page_start': 1, 'page_end': 3, 'order_index': 1}]}
    assert client.put(f"{P}/topics/{topics[0]['id']}/materials", headers=headers, json=mapping).status_code == 200
    newest = client.post(f"{P}/documents/{document['id']}/versions", headers=headers, files={'file': ('new.pdf', pdf_bytes(2), 'application/pdf')})
    assert newest.status_code == 201 and newest.json()['version'] == 2
    login(client, seeded, 'student')
    response = client.get(url, headers={'Range': 'bytes=0-9'})
    assert response.status_code == 206 and response.content.startswith(b'%PDF-') and len(response.content) == 10
    assert response.headers['content-range'].startswith('bytes 0-9/')
    assert client.get(url, headers={'Range': 'bytes=999999-'}).status_code == 416
    topic = client.get(f"{P}/course-runs/{run['id']}/topics").json()['items'][0]
    assert topic['materials'][0]['document_version_id'] == version['id']
    assert 'storage_key' not in str(client.get(f"{P}/course-runs/{run['id']}/documents").json())
    client.cookies.clear()
    assert client.get(url).status_code == 401


def test_pdf_validation_and_atomic_cleanup(client, seeded):
    headers = login(client, seeded, 'teacher')
    course = client.get(f'{P}/courses').json()['items'][0]
    for payload, expected in [(b'not pdf', 415), (b'%PDF-broken', 422), (pdf_bytes(encrypted=True), 422), (pdf_bytes(501), 422), (b'%PDF-' + b' ' * (20 * 1024 * 1024), 413)]:
        response = client.post(f"{P}/courses/{course['id']}/documents", headers=headers, data={'code': 'INVALID', 'title': 'Invalid'}, files={'file': ('bad.pdf', payload, 'application/pdf')})
        assert response.status_code == expected, response.text
    assert client.get(f"{P}/courses/{course['id']}/documents").json()['total'] == 0
    from app.config import get_settings
    storage = get_settings().pdf_storage_path
    assert not storage.exists() or not list(storage.iterdir())


def test_question_source_and_student_answer_bank_forbidden(client, seeded):
    headers, run, topics, doc = setup_content(client, seeded)
    version = doc['versions'][0]['id']
    quiz = make_quiz(client, headers, topics[0], version)
    login(client, seeded, 'student')
    assert client.get(f"{P}/topics/{topics[0]['id']}/question-versions").status_code == 403
    assert client.get(f"{P}/quiz-versions/{quiz['id']}").status_code == 403
    metadata = client.get(f"{P}/course-runs/{run['id']}/topics/{topics[0]['id']}/quiz").json()
    assert 'correct_option' not in str(metadata) and 'explanation' not in str(metadata)


def test_attempt_idempotency_resume_revision_and_server_grading(client, seeded, database):
    headers, run, topics, doc = setup_content(client, seeded)
    quiz = make_quiz(client, headers, topics[0], doc['versions'][0]['id'])
    headers = login(client, seeded, 'student')
    key = str(uuid4())
    response = begin(client, headers, run, topics[0], quiz, key)
    assert response.status_code == 201
    attempt = response.json()
    assert 'correct_option' not in str(attempt) and 'sources' not in str(attempt)
    assert begin(client, headers, run, topics[0], quiz, key).json()['id'] == attempt['id']
    assert begin(client, headers, run, topics[0], quiz).json()['id'] == attempt['id']
    answers = [{'quiz_version_item_id': item['quiz_version_item_id'], 'selected_option': 'B'} for item in attempt['items']]
    url = f"{P}/attempts/{attempt['id']}"
    foreign = [{'quiz_version_item_id': str(uuid4()), 'selected_option': 'B'}]
    assert client.put(url + '/answers', headers=headers, json={'expected_revision': 0, 'answers': foreign}).status_code == 422
    saved = client.put(url + '/answers', headers=headers, json={'expected_revision': 0, 'answers': answers})
    assert saved.status_code == 200 and saved.json()['answer_revision'] == 1
    assert client.get(url).json()['items'][0]['selected_option'] == 'B'
    assert client.put(url + '/answers', headers=headers, json={'expected_revision': 0, 'answers': []}).status_code == 409
    assert client.post(url + '/submit', headers=headers, json={'expected_revision': 0}).status_code == 409
    result = client.post(url + '/submit', headers=headers, json={'expected_revision': 1})
    assert result.status_code == 200, result.text
    assert result.json()['score_percent'] == 100 and result.json()['passed_for_attempt_version']
    assert result.json()['counts_for_current_mastery'] and result.json()['items'][0]['correct_option'] == 'B'
    assert client.post(url + '/submit', headers=headers, json={'expected_revision': 1}).json() == result.json()
    assert client.put(url + '/answers', headers=headers, json={'expected_revision': 1, 'answers': []}).status_code == 409
    assert begin(client, headers, run, topics[0], quiz).json()['id'] != attempt['id']
    headers = login(client, seeded, 'teacher')
    assert client.patch(f"{P}/course-runs/{run['id']}", headers=headers, json={'timezone': 'UTC'}).status_code == 409
    report = client.get(f"{P}/course-runs/{run['id']}/report").json()['items'][0]
    assert report['attempt_count'] == 2 and report['latest_results'][0]['score_percent'] == 100


def test_quiz_republication_keeps_old_attempt_snapshot(client, seeded):
    headers, run, topics, doc = setup_content(client, seeded)
    first = make_quiz(client, headers, topics[0], doc['versions'][0]['id'])
    student = login(client, seeded, 'student')
    old = begin(client, student, run, topics[0], first).json()
    headers = login(client, seeded, 'teacher')
    second = make_quiz(client, headers, topics[0], doc['versions'][0]['id'])
    student = login(client, seeded, 'student')
    assert begin(client, student, run, topics[0], first).status_code == 409
    result = client.post(f"{P}/attempts/{old['id']}/submit", headers=student, json={'expected_revision': 0})
    assert result.status_code == 200 and result.json()['score_percent'] == 0
    assert result.json()['counts_for_current_mastery'] is False
    assert begin(client, student, run, topics[0], second).status_code == 201


def test_events_atomic_dedup_conflict_and_server_time(client, seeded, database):
    headers, run, topics, doc = setup_content(client, seeded)
    headers = login(client, seeded, 'student')
    sample = event(doc['versions'][0]['id'], client_observed_at='1999-01-01T00:00:00Z')
    before = datetime.now(timezone.utc)
    result = send_events(client, headers, run, [sample, sample])
    assert result.status_code == 200 and result.json()['accepted'] == result.json()['duplicate'] == 1
    assert send_events(client, headers, run, [sample]).json()['duplicate'] == 1
    fresh = event(doc['versions'][0]['id'])
    assert send_events(client, headers, run, [fresh, {**sample, 'pdf_page': 2}]).status_code == 409
    assert send_events(client, headers, run, [fresh, event(doc['versions'][0]['id'], pdf_page=4)]).status_code == 422
    assert send_events(client, headers, run, [{**fresh, 'occurred_at': '2000-01-01T00:00:00Z'}]).status_code == 422
    logs = client.get(f"{P}/course-runs/{run['id']}/events").json()
    assert logs['total'] == 1
    row = logs['items'][0]
    assert row['occurred_at'] == row['received_at'] and row['data_origin'] == 'real'
    assert datetime.fromisoformat(row['occurred_at']) >= before
    headers = login(client, seeded, 'teacher')
    assert client.patch(f"{P}/course-runs/{run['id']}", headers=headers, json={'course_run_start_date': '2026-10-04'}).status_code == 409
    assert send_events(client, headers, run, [fresh]).status_code == 403
    assert client.get(f"{P}/course-runs/{run['id']}/report").json()['items'][0]['page_views'] == 1


def test_closed_synthetic_and_revoked_enrollment_are_read_only(client, seeded, database):
    headers, run, topics, doc = setup_content(client, seeded)
    quiz = make_quiz(client, headers, topics[0], doc['versions'][0]['id'])
    headers = login(client, seeded, 'student')
    attempt = begin(client, headers, run, topics[0], quiz).json()
    with database.begin() as connection:
        connection.execute(text("UPDATE course_runs SET status='closed'"))
    assert client.get(f"{P}/attempts/{attempt['id']}").status_code == 200
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{doc['versions'][0]['id']}/content").status_code == 200
    assert client.post(f"{P}/attempts/{attempt['id']}/submit", headers=headers, json={'expected_revision': 0}).status_code == 409
    assert send_events(client, headers, run, [event(doc['versions'][0]['id'])]).status_code == 409
    with database.begin() as connection:
        connection.execute(text("UPDATE course_runs SET status='active', data_origin='synthetic'"))
    assert begin(client, headers, run, topics[0], quiz).status_code == 409
    with database.begin() as connection:
        connection.execute(text("UPDATE enrollments SET status='inactive'"))
    assert client.get(f"{P}/attempts/{attempt['id']}").status_code == 404
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{doc['versions'][0]['id']}/content").status_code == 404


def test_concurrent_event_retry_and_attempt_begin(client, seeded, database):
    headers, run, topics, doc = setup_content(client, seeded)
    quiz = make_quiz(client, headers, topics[0], doc['versions'][0]['id'])
    headers = login(client, seeded, 'student')
    sample = event(doc['versions'][0]['id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        logs = list(pool.map(lambda _: send_events(client, headers, run, [sample]), range(2)))
    assert sorted(response.json()['accepted'] for response in logs) == [0, 1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda _: begin(client, headers, run, topics[0], quiz), range(2)))
    assert sorted(response.status_code for response in attempts) == [200, 201]
    assert attempts[0].json()['id'] == attempts[1].json()['id']


def test_cross_course_documents_materials_sources_and_attempt_ownership(client, seeded):
    headers, run, topics, doc = setup_content(client, seeded)
    quiz = make_quiz(client, headers, topics[0], doc['versions'][0]['id'])
    other_course = client.post(f'{P}/courses', headers=headers, json={'code': 'OTHER', 'title': 'Other'}).json()
    other_topic = client.post(f"{P}/courses/{other_course['id']}/topics", headers=headers, json={'code': 'T1', 'title': 'Other', 'order_index': 1, 'objectives': []}).json()
    assert client.put(f"{P}/topics/{other_topic['id']}/materials", headers=headers, json={'items': [{'document_version_id': doc['versions'][0]['id'], 'page_start': 1, 'page_end': 2, 'order_index': 1}]}).status_code == 404
    student = login(client, seeded, 'student')
    assert begin(client, student, run, other_topic, quiz).status_code == 404
    attempt = begin(client, student, run, topics[0], quiz).json()
    client.cookies.clear()
    client.post(f'{P}/auth/register', headers={'Origin': ORIGIN}, json={'email': 'outsider@example.com', 'password': 'OutsiderPassword123!', 'display_name': 'Outsider'})
    client.post(f'{P}/auth/login', headers={'Origin': ORIGIN}, json={'email': 'outsider@example.com', 'password': 'OutsiderPassword123!'})
    assert client.get(f"{P}/attempts/{attempt['id']}").status_code == 404
    assert client.get(f"{P}/course-runs/{run['id']}/events").status_code == 404


def test_streamed_request_limit_before_multipart_parser(client):
    data = iter([b'x' * (1024 * 1024)] * 22)
    response = client.post(f'{P}/auth/register', headers={'Origin': ORIGIN, 'Content-Type': 'application/json'}, content=data)
    assert response.status_code == 413
