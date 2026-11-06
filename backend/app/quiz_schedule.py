"""Class-specific deadlines pinned to the published quiz version."""
from datetime import timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, NaiveDatetime
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.courses import owner_run
from app.db import get_db
from app.errors import ApiError
from app.learning_models import ClassQuizDeadline, QuizAttempt, QuizVersion
from app.models import Topic
from app.security import AuthContext, require_teacher, utcnow

router = APIRouter(tags=['quiz-schedule'])


class DeadlineInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    due_local: NaiveDatetime | None


def deadline_instant(local, zone):
    instants = {local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc) for fold in (0, 1)}
    valid = [instant for instant in instants if instant.astimezone(zone).replace(tzinfo=None) == local]
    if len(valid) != 1:
        raise ApiError(422, 'DEADLINE_LOCAL_TIME_INVALID', 'Giờ này bị trùng hoặc không tồn tại trong múi giờ lớp.')
    return valid[0]


def schedule_rows(db, run, include_unassigned=False):
    deadline = ClassQuizDeadline
    query = select(QuizVersion, Topic, deadline).join(Topic, Topic.id == QuizVersion.topic_id).outerjoin(
        deadline, (deadline.quiz_version_id == QuizVersion.id) & (deadline.course_run_id == run.id)).where(
        Topic.course_id == run.course_id)
    assigned = deadline.due_at.is_not(None) & deadline.cancelled_at.is_(None)
    query = query.where(or_(QuizVersion.status == 'published', assigned) if include_unassigned else assigned)
    return db.execute(query.order_by(Topic.order_index, QuizVersion.version.desc())).all()


def schedule_item(quiz, topic, deadline, zone=None):
    due = deadline.due_at if deadline and deadline.cancelled_at is None else None
    return dict(quiz_version_id=quiz.id, version=quiz.version, topic_id=topic.id, topic_code=topic.code,
                title=topic.title, current=quiz.status == 'published',
                due_at=due, due_local=due.astimezone(zone).replace(tzinfo=None).isoformat(timespec='minutes') if due and zone else None)


def learner_schedule(db, run, enrollment, now):
    rows = schedule_rows(db, run)
    if not rows:
        return []
    attempts = db.execute(select(QuizAttempt.quiz_version_id, func.min(QuizAttempt.completed_at),
        func.min(QuizAttempt.graded_at)).where(QuizAttempt.enrollment_id == enrollment.id,
        QuizAttempt.quiz_version_id.in_([quiz.id for quiz, _, _ in rows]),
        QuizAttempt.status == 'completed', QuizAttempt.completed_at <= now).group_by(QuizAttempt.quiz_version_id))
    submitted = {version_id: (first, graded) for version_id, first, graded in attempts}
    items = []
    for quiz, topic, deadline in rows:
        first, graded = submitted.get(quiz.id, (None, None))
        if first:
            status = 'submitted_on_time' if first <= deadline.due_at else 'submitted_late'
        elif quiz.status != 'published':
            status = 'archived'
        elif now > deadline.due_at:
            status = 'overdue'
        else:
            status = 'due_soon' if deadline.due_at - now <= timedelta(days=3) else 'upcoming'
        items.append(dict(**schedule_item(quiz, topic, deadline), status=status, submitted_at=first,
                          graded=graded is not None and graded <= now))
    return sorted(items, key=lambda item: (item['due_at'], item['topic_code'], item['version']))


@router.get('/teaching/runs/{run_id}/quiz-schedule')
def teaching_schedule(run_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    run, _ = owner_run(db, run_id, context.user.id)
    zone = ZoneInfo(run.timezone)
    return {'items': [schedule_item(*row, zone) for row in schedule_rows(db, run, include_unassigned=True)]}


@router.put('/teaching/runs/{run_id}/quiz-schedule/{version_id}')
def set_deadline(run_id: UUID, version_id: UUID, body: DeadlineInput,
                 context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    run, _ = owner_run(db, run_id, context.user.id, lock=True)
    row = db.execute(select(QuizVersion, Topic).join(Topic).where(
        QuizVersion.id == version_id, Topic.course_id == run.course_id)).one_or_none()
    if row is None:
        raise ApiError(404, 'QUIZ_NOT_FOUND', 'Không tìm thấy quiz trong lớp này.')
    quiz, topic = row
    if run.data_origin != 'real' or quiz.status != 'published':
        raise ApiError(409, 'SCHEDULE_READ_ONLY', 'Chỉ chỉnh hạn cho quiz đang công bố trong lớp thật.')
    deadline = db.get(ClassQuizDeadline, (run.id, quiz.id))
    zone = ZoneInfo(run.timezone)
    if body.due_local is None:
        if deadline and deadline.cancelled_at is None:
            deadline.cancelled_at = utcnow()
    else:
        due_at = deadline_instant(body.due_local, zone)
        if deadline:
            deadline.due_at, deadline.cancelled_at = due_at, None
        else:
            deadline = ClassQuizDeadline(course_run_id=run.id, quiz_version_id=quiz.id, due_at=due_at)
            db.add(deadline)
    result = schedule_item(quiz, topic, deadline, zone)
    db.commit()
    return result
