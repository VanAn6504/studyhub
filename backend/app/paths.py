"""path_rules_v1: current-version mastery, prerequisites first, immutable revisions."""
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.guidance_models import LearningPath
from app.learning_models import Document, DocumentVersion, QuizAttempt, QuizItem, QuizVersion, TopicMaterial
from app.models import Course, CourseRun, Enrollment, Topic, TopicPrerequisite
from app.security import AuthContext, get_auth, utcnow

router = APIRouter(tags=['learning-path'])


def lock_enrollment(db, run, enrollment):
    # Same ordering as grading/publication/revocation; reads may persist a snapshot.
    course = db.scalar(select(Course).where(Course.id == run.course_id).with_for_update().execution_options(populate_existing=True))
    db.scalar(select(CourseRun).where(CourseRun.id == run.id).with_for_update().execution_options(populate_existing=True))
    db.scalar(select(Enrollment).where(Enrollment.id == enrollment.id).with_for_update().execution_options(populate_existing=True))
    return course


def ensure_path(db, run, enrollment):
    course = db.get(Course, run.course_id)
    topics = db.scalars(select(Topic).where(Topic.course_id == course.id).order_by(Topic.order_index, Topic.id)).all()
    states, attempts = {}, []
    for topic in topics:
        quiz = db.scalar(select(QuizVersion).where(QuizVersion.topic_id == topic.id, QuizVersion.status == 'published'))
        count = db.scalar(select(func.count()).select_from(QuizItem).where(QuizItem.quiz_version_id == quiz.id)) if quiz else 0
        available = bool(quiz and count >= quiz.min_questions)
        attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.enrollment_id == enrollment.id,
            QuizAttempt.quiz_version_id == quiz.id, QuizAttempt.status == 'completed')
            .order_by(QuizAttempt.graded_at.desc(), QuizAttempt.id.desc()).limit(1)) if available else None
        state, score, reason = 'not_available', None, 'quiz_unavailable'
        if available:
            state, reason = 'not_assessed', 'no_current_assessment'
            if attempt:
                score = 100 * attempt.correct_count / attempt.total_questions
                state = 'mastered' if (attempt.total_questions >= quiz.min_questions and
                    100 * attempt.correct_count >= quiz.pass_percent * attempt.total_questions) else 'weak'
                reason = 'quiz_passed' if state == 'mastered' else 'low_quiz_score'
                attempts.append(str(attempt.id))
            elif db.scalar(select(QuizAttempt.id).join(QuizVersion).where(
                    QuizAttempt.enrollment_id == enrollment.id, QuizVersion.topic_id == topic.id,
                    QuizAttempt.status == 'completed').limit(1)):
                reason = 'content_changed'
        states[str(topic.id)] = dict(topic_id=str(topic.id), topic_code=topic.code, title=topic.title,
            order_index=topic.order_index, state=state, score_percent=score, reason=reason,
            attempt_id=str(attempt.id) if attempt else None, quiz_version_id=str(quiz.id) if available else None)
    inputs = {'rules_version': 'path_rules_v1', 'content_revision': course.content_revision, 'input_attempt_ids': sorted(attempts),
              'topic_reasons': {key: item['reason'] for key, item in states.items()}}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    old = db.scalar(select(LearningPath).where(LearningPath.enrollment_id == enrollment.id, LearningPath.input_hash == digest))
    if old:
        return path_output(old)
    prereqs = {key: [] for key in states}
    for edge in db.scalars(select(TopicPrerequisite).where(TopicPrerequisite.course_id == course.id)):
        prereqs[str(edge.topic_id)].append(str(edge.prerequisite_topic_id))
    for values in prereqs.values():
        values.sort(key=lambda key: states[key]['order_index'])
    steps, visited, warnings = [], set(), []

    def visit(key, prerequisite=False):
        if key in visited:
            return
        visited.add(key)
        item = states[key]
        if item['state'] == 'mastered':
            return
        if item['state'] == 'not_available':
            if prerequisite:
                warnings.append({'topic_id': key, 'reason': 'prerequisite_unavailable'})
            return
        for dependency in prereqs[key]:
            visit(dependency, True)
        materials = db.execute(select(TopicMaterial, DocumentVersion, Document)
            .join(DocumentVersion, DocumentVersion.id == TopicMaterial.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(TopicMaterial.topic_id == UUID(key), Document.status == 'published', DocumentVersion.status == 'ready')
            .order_by(TopicMaterial.order_index)).all()
        steps.append({**item, 'position': len(steps) + 1, 'state_at_generation': item['state'],
            'reason': 'unassessed_prerequisite' if prerequisite and item['state'] == 'not_assessed' else item['reason'],
            'prerequisite_topic_ids': prereqs[key], 'materials': [dict(document_version_id=str(v.id),
                title=d.title, document_code=d.code, page_start=m.page_start, page_end=m.page_end) for m, v, d in materials],
            'actions': ['read_material', 'take_quiz'] if materials else ['take_quiz']})

    weak = sorted((key for key, item in states.items() if item['state'] == 'weak'),
                  key=lambda key: (states[key]['score_percent'], states[key]['order_index']))
    for key in weak:
        visit(key)
    for key, item in states.items():
        if item['state'] == 'not_assessed':
            visit(key)
    revision = (db.scalar(select(func.max(LearningPath.revision)).where(LearningPath.enrollment_id == enrollment.id)) or 0) + 1
    row = LearningPath(enrollment_id=enrollment.id, revision=revision, input_hash=digest, generated_at=utcnow(),
        snapshot={**inputs, 'topic_states': list(states.values()), 'steps': steps, 'warnings': warnings,
                  'unavailable_topics': [item for item in states.values() if item['state'] == 'not_available'],
                  'data_origin': run.data_origin})
    db.add(row)
    db.flush()
    return path_output(row)


def path_output(row):
    return {**row.snapshot, 'id': row.id, 'revision': row.revision, 'generated_at': row.generated_at}


@router.get('/course-runs/{run_id}/learning-path')
def learning_path(run_id: UUID, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    from app.quizzes import student_enrollment
    run, enrollment = student_enrollment(db, run_id, context)
    lock_enrollment(db, run, enrollment)
    # Recheck after taking the lock if an enrollment was revoked concurrently.
    run, enrollment = student_enrollment(db, run_id, context)
    result = ensure_path(db, run, enrollment)
    db.commit()
    return result
