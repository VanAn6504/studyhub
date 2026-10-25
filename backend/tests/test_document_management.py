from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from test_learning import P, begin, event, login, make_quiz, pdf_bytes, private_pdf_storage, send_events, setup_content


def test_edit_metadata_preserves_versions_and_updates_materials(client, seeded):
    headers, run, topics, doc = setup_content(client, seeded)
    version = doc['versions'][0]
    mapping = {'items': [{'document_version_id': version['id'], 'page_start': 1, 'page_end': 2, 'order_index': 1}]}
    assert client.put(f"{P}/topics/{topics[0]['id']}/materials", headers=headers, json=mapping).status_code == 200
    revision = client.get(f'{P}/courses').json()['items'][0]['content_revision']
    url = f"{P}/documents/{doc['id']}"
    response = client.patch(url, headers=headers, json={'code': 'NEW_CODE', 'title': 'New title'})
    assert response.status_code == 200
    assert response.json()['versions'] == doc['versions']
    assert client.patch(url, headers=headers, json={'code': 'NEW_CODE', 'title': 'New title'}).status_code == 200
    assert client.get(f'{P}/courses').json()['items'][0]['content_revision'] == revision + 1
    other = client.post(f"{P}/courses/{run['course_id']}/documents", headers=headers, data={'code': 'SECOND', 'title': 'Second'}, files={'file': ('second.pdf', pdf_bytes(), 'application/pdf')})
    assert other.status_code == 201
    assert client.patch(url, headers=headers, json={'code': 'SECOND'}).status_code == 409
    for body in ({'code': ''}, {'title': None}, {'code': 'bad code'}, {'deleted_at': '2026-10-25'}, {}):
        assert client.patch(url, headers=headers, json=body).status_code == 422
    login(client, seeded, 'student')
    material = client.get(f"{P}/course-runs/{run['id']}/topics").json()['items'][0]['materials'][0]
    assert material['document_code'] == 'NEW_CODE' and material['title'] == 'New title'
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{version['id']}/content").content == pdf_bytes()


def test_permanent_delete_removes_files_sources_and_preserves_learning_history(client, seeded, database):
    headers, run, topics, doc = setup_content(client, seeded)
    version = doc['versions'][0]['id']
    quiz = make_quiz(client, headers, topics[0], version)
    assert client.put(f"{P}/topics/{topics[0]['id']}/materials", headers=headers, json={'items': [{'document_version_id': version, 'page_start': 1, 'page_end': 3, 'order_index': 1}]}).status_code == 200
    student_headers = login(client, seeded, 'student')
    attempt = begin(client, student_headers, run, topics[0], quiz).json()
    assert send_events(client, student_headers, run, [event(version)]).status_code == 200
    saved = client.put(f"{P}/attempts/{attempt['id']}/answers", headers=student_headers, json={'expected_revision': 0, 'answers': [{'quiz_version_item_id': item['quiz_version_item_id'], 'selected_option': 'B'} for item in attempt['items']]}).json()
    result = client.post(f"{P}/attempts/{attempt['id']}/submit", headers=student_headers, json={'expected_revision': saved['answer_revision']}).json()
    assert result['score_percent'] == 100
    headers = login(client, seeded, 'teacher')
    url = f"{P}/documents/{doc['id']}"
    revision = client.get(f'{P}/courses').json()['items'][0]['content_revision']
    from app.learning_models import Document, DocumentVersion
    from app.config import get_settings
    with Session(database) as db:
        storage_key = db.get(DocumentVersion, UUID(version)).storage_key
    assert (get_settings().pdf_storage_path / storage_key).is_file()
    assert client.delete(url, headers=headers).status_code == 204
    assert client.delete(url, headers=headers).status_code == 404
    assert not (get_settings().pdf_storage_path / storage_key).exists()
    with Session(database) as db:
        assert db.get(Document, UUID(doc['id'])) is None
        assert db.get(DocumentVersion, UUID(version)).document_id is None
    assert client.get(f'{P}/courses').json()['items'][0]['content_revision'] == revision + 1
    assert client.get(f"{P}/courses/{run['course_id']}/documents").json()['total'] == 0
    assert client.get(f"{P}/courses/{run['course_id']}/topics").json()['items'][0]['materials'] == []
    assert client.patch(url, headers=headers, json={'status': 'published'}).status_code == 404
    assert client.post(url + '/versions', headers=headers, files={'file': ('new.pdf', pdf_bytes(), 'application/pdf')}).status_code == 404
    for suffix in ('content', 'rag'):
        assert client.get(f'{P}/document-versions/{version}/{suffix}').status_code == 404
    assert client.post(f'{P}/document-versions/{version}/rag/enable', headers=headers).status_code == 404
    login(client, seeded, 'student')
    assert client.get(f"{P}/course-runs/{run['id']}/documents").json()['total'] == 0
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{version}/content").status_code == 404
    assert client.get(f"{P}/attempts/{attempt['id']}").json() == result
    assert client.get(f"{P}/course-runs/{run['id']}/events").json()['total'] == 1
    headers = login(client, seeded, 'teacher')
    assert client.post(url + '/restore', headers=headers).status_code == 404
    # A permanently deleted document no longer reserves its code.
    replacement = client.post(f"{P}/courses/{run['course_id']}/documents", headers=headers, data={'code': doc['code'], 'title': 'New document'}, files={'file': ('new.pdf', pdf_bytes(), 'application/pdf')})
    assert replacement.status_code == 201 and replacement.json()['id'] != doc['id']


def test_document_management_requires_owner_and_csrf(client, seeded, database):
    headers, run, _, doc = setup_content(client, seeded)
    url = f"{P}/documents/{doc['id']}"
    assert client.delete(url).status_code == 403
    assert client.put(url + '/file', data={'code': 'No', 'title': 'No'}, files={'file': ('x.pdf', pdf_bytes(), 'application/pdf')}).status_code == 403
    headers = login(client, seeded, 'student')
    assert client.delete(url, headers=headers).status_code == 403
    assert client.put(url + '/file', headers=headers, data={'code': 'No', 'title': 'No'}, files={'file': ('x.pdf', pdf_bytes(), 'application/pdf')}).status_code == 403
    assert client.patch(url, headers=headers, json={'title': 'No'}).status_code == 403
    assert client.get(f"{P}/courses/{run['course_id']}/documents?deleted=true").status_code == 403
    with database.begin() as db:
        db.execute(text("UPDATE users SET role='teacher' WHERE email='student@example.com'"))
    headers = login(client, seeded, 'student')
    assert client.delete(url, headers=headers).status_code == 404
    assert client.put(url + '/file', headers=headers, data={'code': 'No', 'title': 'No'}, files={'file': ('x.pdf', pdf_bytes(), 'application/pdf')}).status_code == 404
    assert client.patch(url, headers=headers, json={'code': 'No'}).status_code == 404
    assert client.get(f"{P}/courses/{run['course_id']}/documents?deleted=true").status_code == 404


def test_delete_cancels_pending_rag_generation(client, seeded, database, monkeypatch):
    from app.rag_models import RagPreparation
    from app.models import User
    from app.security import utcnow
    from app import rag_workflow
    headers, _, _, doc = setup_content(client, seeded)
    version = UUID(doc['versions'][0]['id'])
    generation = uuid4()
    with Session(database) as db:
        teacher_id = db.scalar(select(User.id).where(User.email == 'teacher@example.com'))
        db.add(RagPreparation(document_version_id=version, enabled=True, status='processing', generation_id=generation, started_at=utcnow()))
        db.commit()
    assert client.delete(f"{P}/documents/{doc['id']}", headers=headers).status_code == 204
    called = []
    monkeypatch.setattr(rag_workflow, 'extract_corpus', lambda *args: called.append(True))
    rag_workflow.prepare(version, generation, teacher_id)
    assert called == []
    with Session(database) as db:
        state = db.get(RagPreparation, version)
        assert state is None


@pytest.mark.parametrize('count', [10, 20])
def test_quiz_accepts_full_imported_sets_and_grades_every_question(client, seeded, count):
    headers, run, topics, doc = setup_content(client, seeded)
    ids = []
    for i in range(count):
        response = client.post(f"{P}/topics/{topics[0]['id']}/questions", headers=headers, json={'code': f'Q{i:02}', 'stem': f'Question {i}', 'options': {'A': 'one', 'B': 'two', 'C': 'three', 'D': 'four'}, 'correct_option': 'A', 'explanation': 'Explanation', 'sources': [{'document_version_id': doc['versions'][0]['id'], 'pdf_page': 1}]})
        assert response.status_code == 201
        ids.append(response.json()['id'])
    response = client.post(f"{P}/topics/{topics[0]['id']}/quiz-versions", headers=headers, json={'question_version_ids': ids})
    assert response.status_code == 201 and response.json()['question_count'] == count
    quiz = response.json()
    assert client.post(f"{P}/quiz-versions/{quiz['id']}/publish", headers=headers).status_code == 200
    headers = login(client, seeded, 'student')
    attempt = begin(client, headers, run, topics[0], quiz).json()
    assert len(attempt['items']) == count and 'correct_option' not in str(attempt)
    saved = client.put(f"{P}/attempts/{attempt['id']}/answers", headers=headers, json={'expected_revision': 0, 'answers': [{'quiz_version_item_id': item['quiz_version_item_id'], 'selected_option': 'A'} for item in attempt['items']]}).json()
    result = client.post(f"{P}/attempts/{attempt['id']}/submit", headers=headers, json={'expected_revision': saved['answer_revision']}).json()
    assert result['score_percent'] == 100 and result['total_questions'] == count and result['correct_count'] == count


def test_replace_pdf_is_atomic_and_retires_old_sources(client, seeded, database):
    from app.config import get_settings
    from app.learning_models import DocumentVersion
    headers, run, topics, doc = setup_content(client, seeded)
    old = doc['versions'][0]
    quiz = make_quiz(client, headers, topics[0], old['id'])
    assert client.put(f"{P}/topics/{topics[0]['id']}/materials", headers=headers, json={'items': [{'document_version_id': old['id'], 'page_start': 1, 'page_end': 3, 'order_index': 1}]}).status_code == 200
    with Session(database) as db:
        path = get_settings().pdf_storage_path / db.get(DocumentVersion, UUID(old['id'])).storage_key
    url = f"{P}/documents/{doc['id']}/file"
    data = {'code': 'NEW', 'title': 'Replacement'}
    for content, status in ((b'not PDF', 415), (pdf_bytes(encrypted=True), 422)):
        assert client.put(url, headers=headers, data=data, files={'file': ('new.pdf', content, 'application/pdf')}).status_code == status
        assert path.is_file()
        current = client.get(f"{P}/courses/{run['course_id']}/documents").json()['items'][0]
        assert current['code'] == doc['code'] and current['status'] == 'published' and current['versions'] == doc['versions']
    response = client.put(url, headers=headers, data=data, files={'file': ('new.pdf', pdf_bytes(1), 'application/pdf')})
    assert response.status_code == 200
    updated = response.json()
    assert updated['id'] == doc['id'] and updated['code'] == 'NEW' and updated['title'] == 'Replacement'
    assert updated['status'] == 'draft' and len(updated['versions']) == 1
    new = updated['versions'][0]
    assert new['id'] != old['id'] and new['page_count'] == 1 and new['version'] == 2
    assert not path.exists()
    assert client.get(f"{P}/document-versions/{old['id']}/content").status_code == 404
    assert client.get(f"{P}/document-versions/{old['id']}/rag").status_code == 404
    assert client.get(f"{P}/document-versions/{new['id']}/content").content == pdf_bytes(1)
    assert client.get(f"{P}/document-versions/{new['id']}/rag").json()['enabled'] is False
    assert client.get(f"{P}/courses/{run['course_id']}/topics").json()['items'][0]['materials'] == []
    assert client.get(f"{P}/quiz-versions/{quiz['id']}").json()['status'] == 'published'
    # Old question sources retain their IDs; they never silently point to the replacement.
    assert client.get(f"{P}/topics/{topics[0]['id']}/question-versions").json()['items'][0]['sources'][0]['document_version_id'] == old['id']
    student_headers = login(client, seeded, 'student')
    assert client.get(f"{P}/course-runs/{run['id']}/documents").json()['total'] == 0
    attempt = begin(client, student_headers, run, topics[0], quiz)
    assert attempt.status_code == 201 and len(attempt.json()['items']) == 3


def test_pdf_cleanup_retries_file_failure_without_restoring_document(client, seeded, database, monkeypatch):
    from pathlib import Path
    from app.config import get_settings
    from app.learning_models import Document, DocumentVersion, PdfFileDeletion
    from app.pdf_cleanup import cleanup_pdf_files
    headers, _, _, doc = setup_content(client, seeded)
    with Session(database) as db:
        key = db.get(DocumentVersion, UUID(doc['versions'][0]['id'])).storage_key
    original = Path.unlink
    def fail_target(path, *args, **kwargs):
        if path.name == key:
            raise PermissionError('Temporary fixture lock')
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', fail_target)
        assert client.delete(f"{P}/documents/{doc['id']}", headers=headers).status_code == 204
    with Session(database) as db:
        assert db.get(Document, UUID(doc['id'])) is None
        assert db.get(PdfFileDeletion, key) is not None
    cleanup_pdf_files()
    assert not (get_settings().pdf_storage_path / key).exists()
    with Session(database) as db:
        assert db.get(PdfFileDeletion, key) is None


@pytest.mark.parametrize('operation', ['delete', 'replace'])
def test_stale_rag_and_document_sessions_recheck_after_course_lock(client, seeded, database, operation):
    from types import SimpleNamespace
    from app.errors import ApiError
    from app.learning_models import Document, DocumentVersion
    from app.models import User
    from app.rag import owned_version
    from app.resources import owned_document
    headers, _, _, doc = setup_content(client, seeded)
    document_id, version_id = UUID(doc['id']), UUID(doc['versions'][0]['id'])
    with Session(database, expire_on_commit=False) as db:
        cached_document = db.get(Document, document_id)
        cached_version = db.get(DocumentVersion, version_id)
        teacher_id = db.scalar(select(User.id).where(User.email == 'teacher@example.com'))
        context = SimpleNamespace(user=SimpleNamespace(id=teacher_id))
        if operation == 'delete':
            assert client.delete(f'{P}/documents/{document_id}', headers=headers).status_code == 204
        else:
            assert client.put(f'{P}/documents/{document_id}/file', headers=headers, data={'code': 'NEW', 'title': 'New'}, files={'file': ('new.pdf', pdf_bytes(1), 'application/pdf')}).status_code == 200
        assert cached_document is not None and cached_version.document_id == document_id
        with pytest.raises(ApiError) as failure:
            owned_version(db, version_id, context, lock=True)
        assert failure.value.status == 404
        if operation == 'delete':
            with pytest.raises(ApiError) as failure:
                owned_document(db, document_id, teacher_id)
            assert failure.value.status == 404
