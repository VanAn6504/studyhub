"""features_v1, shared names/order and timezone-safe inclusive day cutoffs."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.learning_models import LearningEvent, QuizAttempt, QuizVersion

FEATURES_A = ['active_days', 'material_interactions', 'days_since_last_activity']
FEATURES_B = FEATURES_A + ['assessment_count', 'mean_assessment_score', 'has_assessment']
SCHEMA_VERSION = 'features_v1'
CUTOFF_DAY = 42


def cutoff_bounds(start_date, timezone_name, cutoff=CUTOFF_DAY):
    zone = ZoneInfo(timezone_name)
    lower = datetime.combine(start_date, time.min, zone).astimezone(timezone.utc)
    upper = datetime.combine(start_date + timedelta(days=cutoff + 1), time.min, zone).astimezone(timezone.utc)
    return lower, upper


def studyhub_features(db, run, enrollment, cutoff=CUTOFF_DAY):
    lower, upper = cutoff_bounds(run.course_run_start_date, run.timezone, cutoff)
    events = db.scalars(select(LearningEvent).where(LearningEvent.enrollment_id == enrollment.id,
        LearningEvent.type == 'page_view', LearningEvent.schema_version == 'learning_event_v1',
        LearningEvent.data_origin == run.data_origin, LearningEvent.occurred_at >= lower,
        LearningEvent.occurred_at < upper, LearningEvent.received_at < upper)).all()
    days = {(event.occurred_at.astimezone(ZoneInfo(run.timezone)).date() - run.course_run_start_date).days for event in events}
    first = {}
    for attempt, topic_id in db.execute(select(QuizAttempt, QuizVersion.topic_id).join(QuizVersion).where(
            QuizAttempt.enrollment_id == enrollment.id, QuizAttempt.status == 'completed',
            QuizAttempt.graded_at >= lower, QuizAttempt.graded_at < upper)
            .order_by(QuizAttempt.graded_at, QuizAttempt.id)):
        if topic_id not in first:
            first[topic_id] = 100 * attempt.correct_count / attempt.total_questions
    return dict(active_days=len(days), material_interactions=len(events),
        days_since_last_activity=cutoff - max(days) if days else cutoff + 1,
        assessment_count=len(first), mean_assessment_score=sum(first.values()) / len(first) if first else None,
        has_assessment=int(bool(first)))
