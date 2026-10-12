from sqlalchemy import text
from conftest import ORIGIN

P = '/api/v1'


def test_topic_edit_preserves_links_and_only_changes_revision_when_needed(teacher, database):
    client, headers = teacher
    course = client.get(f'{P}/courses').json()['items'][0]
    topic = client.get(f"{P}/courses/{course['id']}/topics").json()['items'][0]
    body = {key: topic[key] for key in ('code', 'title', 'order_index', 'objectives')}
    body['title'] = 'Chủ đề cập nhật'
    result = client.patch(f"{P}/topics/{topic['id']}", headers=headers, json=body)
    assert result.status_code == 200
    assert result.json()['title'] == body['title']
    assert result.json()['prerequisite_topic_ids'] == topic['prerequisite_topic_ids']
    assert client.get(f'{P}/courses').json()['items'][0]['content_revision'] == course['content_revision'] + 1
    assert client.patch(f"{P}/topics/{topic['id']}", headers=headers, json=body).status_code == 200
    assert client.get(f'{P}/courses').json()['items'][0]['content_revision'] == course['content_revision'] + 1
    assert client.patch(f"{P}/topics/{topic['id']}", json=body).status_code == 403
    assert client.patch(f"{P}/topics/{topic['id']}", headers=headers, json={**body, 'order_index': 0}).status_code == 422
    with database.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM topics')) == 8


def test_topic_edit_duplicate_code_rolls_back_and_extra_fields_rejected(teacher):
    client, headers = teacher
    course = client.get(f'{P}/courses').json()['items'][0]
    topics = client.get(f"{P}/courses/{course['id']}/topics").json()['items']
    body = {key: topics[0][key] for key in ('code', 'title', 'order_index', 'objectives')}
    assert client.patch(f"{P}/topics/{topics[0]['id']}", headers=headers, json={**body, 'code': topics[1]['code']}).status_code == 409
    assert client.get(f'{P}/courses').json()['items'][0]['content_revision'] == course['content_revision']
    assert client.patch(f"{P}/topics/{topics[0]['id']}", headers=headers, json={**body, 'course_id': course['id']}).status_code == 422


def test_enrollment_list_owner_fields_pagination_and_student_denied(teacher, seeded):
    client, _ = teacher
    run = client.get(f'{P}/course-runs').json()['items'][0]
    result = client.get(f"{P}/course-runs/{run['id']}/enrollments?limit=1")
    assert result.status_code == 200
    page = result.json()
    assert page['total'] == 1 and len(page['items']) == 1
    assert set(page['items'][0]) == {'id', 'student_id', 'student_email', 'display_name', 'status'}
    assert page['items'][0]['student_email'] == 'student@example.com'
    assert client.get(f"{P}/course-runs/{run['id']}/enrollments?offset=1").json()['items'] == []
    client.cookies.clear()
    assert client.post(f'{P}/auth/login', headers={'Origin': ORIGIN}, json={'email': 'student@example.com', 'password': seeded['student']}).status_code == 200
    assert client.get(f"{P}/course-runs/{run['id']}/enrollments").status_code == 403


def test_new_workspace_endpoints_reject_another_teacher(client, database):
    body = {'email': 'workspace.other@example.com', 'password': 'IndependentTest123!', 'display_name': 'Other'}
    client.post(f'{P}/auth/register', headers={'Origin': ORIGIN}, json=body)
    with database.begin() as db:
        topic_id = str(db.scalar(text('SELECT id FROM topics LIMIT 1')))
        run_id = str(db.scalar(text('SELECT id FROM course_runs LIMIT 1')))
        db.execute(text("UPDATE users SET role='teacher' WHERE email='workspace.other@example.com'"))
    auth = client.post(f'{P}/auth/login', headers={'Origin': ORIGIN}, json={'email': body['email'], 'password': body['password']}).json()
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': auth['csrf_token']}
    assert client.get(f'{P}/course-runs/{run_id}/enrollments').status_code == 404
    assert client.patch(f'{P}/topics/{topic_id}', headers=headers, json={'code': 'X', 'title': 'Other', 'order_index': 1, 'objectives': []}).status_code == 404
