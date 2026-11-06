"""On-demand risk snapshots for completed calendar days; independent of day 42."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.activity import activity_resource, eligible_page_views
from app.config import get_settings
from app.db import get_db
from app.engagement_features import MAX_DAY, MIN_DAY, day_bounds, snapshot_features
from app.guidance_models import ModelVersion, Prediction
from app.learning_models import DocumentVersion, LearningEvent
from app.model_runtime import ArtifactUnavailable, load_artifact, predict_explain
from app.paths import lock_enrollment
from app.predictions import EmptyInput, prediction_output
from app.quizzes import student_enrollment
from app.security import AuthContext, get_auth, utcnow

router = APIRouter(tags=['engagement forecast'])


def forecast(db, run, enrollment, compute=False):
    day, start, end = day_bounds(run, utcnow())
    base = dict(day=day, cutoff_end_at=end if day >= 0 else None, risk_score=None,
                data_origin=run.data_origin, transport_status='unvalidated')
    if run.data_origin != 'real':
        return {**base, 'status': 'outside_range'}
    if day < MIN_DAY:
        return {**base, 'status': 'not_ready'}
    if day > MAX_DAY:
        return {**base, 'status': 'outside_range'}
    try:
        metadata, model, background = load_artifact(get_settings().engagement_artifact_path, daily=True)
        if not any(lower <= day <= upper for lower, upper in metadata['supported_ranges']):
            return {**base, 'status': 'outside_range'}
        query = select(Prediction).join(ModelVersion).where(
            Prediction.enrollment_id == enrollment.id, Prediction.cutoff_end_at == end,
            ModelVersion.code == metadata['code'], ModelVersion.artifact_sha256 == metadata['artifact_sha256'],
            ModelVersion.metadata_snapshot == metadata)
        cached = db.scalar(query)
        if cached:
            return prediction_output(cached)
        if not compute:
            return {**base, 'status': 'not_computed'}
        local_day = func.date(func.timezone(run.timezone, LearningEvent.occurred_at))
        activity = db.execute(select(local_day, activity_resource()).select_from(LearningEvent).join(
            DocumentVersion, DocumentVersion.id == LearningEvent.document_version_id).where(
            *eligible_page_views(run, enrollment, start), LearningEvent.occurred_at < end,
            LearningEvent.received_at < end).distinct()).all()
        features = snapshot_features(run, day, activity)
        score, explanation = predict_explain(model, background, features, metadata['feature_order'])
        db.execute(insert(ModelVersion).values(code=metadata['code'], artifact_sha256=metadata['artifact_sha256'],
            metadata_snapshot=metadata).on_conflict_do_nothing(index_elements=['code']))
        version = db.scalar(select(ModelVersion).where(ModelVersion.code == metadata['code']))
        if version.artifact_sha256 != metadata['artifact_sha256'] or version.metadata_snapshot != metadata:
            raise ArtifactUnavailable()
    except (ArtifactUnavailable, ValueError, RuntimeError, KeyError, TypeError):
        db.rollback()
        return {**base, 'status': 'model_unavailable'}

    threshold = metadata['threshold']
    snapshot = {**base, 'cutoff_end_at': end.isoformat(), 'risk_score': score, 'threshold': threshold,
                'threshold_exceeded': score >= threshold, 'model_code': version.code,
                'explanation': explanation, 'feature_snapshot': features,
                'feature_schema_version': metadata['feature_schema_version'],
                'calibration_status': metadata['calibration_status']}
    row = Prediction(enrollment_id=enrollment.id, model_version_id=version.id, cutoff_end_at=end,
                     status='ok', risk_score=score, snapshot=snapshot, computed_at=utcnow())
    db.add(row)
    db.commit()
    return prediction_output(row)


@router.get('/course-runs/{run_id}/engagement-forecast')
def read_forecast(run_id: UUID, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run, enrollment = student_enrollment(db, run_id, context)
    return forecast(db, run, enrollment)


@router.post('/course-runs/{run_id}/engagement-forecast')
def refresh_forecast(run_id: UUID, body: EmptyInput = EmptyInput(),
                     context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run, enrollment = student_enrollment(db, run_id, context)
    lock_enrollment(db, run, enrollment)
    run, enrollment = student_enrollment(db, run_id, context)
    return forecast(db, run, enrollment, compute=True)
