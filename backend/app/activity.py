"""Atomic, idempotent learning events with server time and enrollment provenance."""
from collections import defaultdict, deque
from threading import Lock
import time
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.courses import Limit, Offset, owner_run
from app.db import get_db
from app.errors import ApiError
from app.learning_models import LearningEvent, QuizAttempt, QuizVersion
from app.learning_schemas import EventsInput
from app.models import Enrollment, User
from app.quizzes import attempt_output, student_enrollment
from app.resources import version_access
from app.security import AuthContext, get_auth, require_teacher, utcnow

router = APIRouter(tags=['activity'])
_event_hits = defaultdict(deque)
_rate_lock = Lock()


def event_rate_limit(user_id):
    now = time.monotonic()
    with _rate_lock:
        for key in list(_event_hits):
            while _event_hits[key] and _event_hits[key][0] <= now - 60:
                _event_hits[key].popleft()
            if not _event_hits[key]:
                del _event_hits[key]
        hits = _event_hits[user_id]
        if len(hits) >= 120:
            raise ApiError(429, 'EVENT_RATE_LIMIT', 'Gửi log quá nhanh. Vui lòng thử lại sau.')
        hits.append(now)


def event_identity(event):
    return event.type, event.document_version_id, event.pdf_page, event.viewer_session_id


@router.post('/course-runs/{run_id}/events')
def record_events(run_id: UUID, body: EventsInput, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run, enrollment = student_enrollment(db, run_id, context, writing=True)
    event_rate_limit(context.user.id)
    now = utcnow()
    # Validate the entire batch before any insert; the enrollment lock serializes
    # same-student retries, with a database UNIQUE constraint as the final guard.
    for event in body.events:
        version, _ = version_access(db, event.document_version_id, run.course_id, published=True)
        if event.pdf_page is not None and event.pdf_page > version.page_count:
            raise ApiError(422, 'PDF_PAGE_INVALID', 'Trang log nằm ngoài PDF.')
    seen = {event.client_event_id: event for event in db.scalars(select(LearningEvent).where(
        LearningEvent.enrollment_id == enrollment.id,
        LearningEvent.client_event_id.in_([event.client_event_id for event in body.events])))}
    accepted = duplicate = 0
    results = []
    for event in body.events:
        old = seen.get(event.client_event_id)
        if old is not None:
            if event_identity(old) != event_identity(event):
                raise ApiError(409, 'EVENT_ID_CONFLICT', 'ID log đã dùng với nội dung khác.')
            duplicate += 1
            status = 'duplicate'
        else:
            row = LearningEvent(enrollment_id=enrollment.id, **event.model_dump(), schema_version=body.schema_version,
                                occurred_at=now, received_at=now, data_origin=run.data_origin)
            db.add(row)
            seen[event.client_event_id] = row
            accepted += 1
            status = 'accepted'
        results.append({'client_event_id': event.client_event_id, 'status': status})
    db.commit()
    return {'accepted': accepted, 'duplicate': duplicate, 'event_results': results, 'server_received_at': now}


@router.get('/course-runs/{run_id}/events')
def list_events(run_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    if context.user.role == 'teacher':
        owner_run(db, run_id, context.user.id)
        enrollment_ids = select(Enrollment.id).where(Enrollment.course_run_id == run_id)
    else:
        _, enrollment = student_enrollment(db, run_id, context)
        enrollment_ids = [enrollment.id]
    query = select(LearningEvent).where(LearningEvent.enrollment_id.in_(enrollment_ids))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(LearningEvent.occurred_at.desc(), LearningEvent.id).limit(limit).offset(offset))
    fields = ('id', 'enrollment_id', 'client_event_id', 'viewer_session_id', 'type', 'document_version_id', 'pdf_page',
              'schema_version', 'occurred_at', 'received_at', 'data_origin')
    return {'items': [{key: getattr(row, key) for key in fields} for row in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.get('/course-runs/{run_id}/report')
def report(run_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    run, _ = owner_run(db, run_id, context.user.id)
    query = select(Enrollment, User).join(User, User.id == Enrollment.student_id).where(Enrollment.course_run_id == run.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = []
    for enrollment, user in db.execute(query.order_by(User.email, Enrollment.id).limit(limit).offset(offset)):
        page_views = db.scalar(select(func.count()).select_from(LearningEvent).where(LearningEvent.enrollment_id == enrollment.id, LearningEvent.type == 'page_view'))
        attempts = db.scalars(select(QuizAttempt).where(QuizAttempt.enrollment_id == enrollment.id).order_by(QuizAttempt.started_at, QuizAttempt.id)).all()
        latest = {}
        for attempt in attempts:
            quiz = db.get(QuizVersion, attempt.quiz_version_id)
            if attempt.status == 'completed':
                latest[quiz.topic_id] = attempt
        rows.append({'enrollment_id': enrollment.id, 'student_email': user.email, 'display_name': user.display_name,
                     'enrollment_status': enrollment.status, 'page_views': page_views, 'attempt_count': len(attempts),
                     'latest_results': [attempt_output(db, attempt) for attempt in latest.values()]})
    return {'items': rows, 'total': total, 'limit': limit, 'offset': offset, 'data_origin': run.data_origin}
