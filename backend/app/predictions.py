"""Cutoff-guarded experimental risk, isolated from topic mastery and path ordering."""
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.features import CUTOFF_DAY, cutoff_bounds, studyhub_features
from app.guidance_models import ModelVersion, Prediction
from app.model_runtime import ArtifactUnavailable, load_artifact, predict_explain
from app.paths import lock_enrollment
from app.quizzes import student_enrollment
from app.security import AuthContext, get_auth, utcnow

router = APIRouter(tags=['predictions'])


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


def base_output(run):
    _, end = cutoff_bounds(run.course_run_start_date, run.timezone)
    return {'cutoff_day': CUTOFF_DAY, 'cutoff_end_at': end, 'risk_score': None,
            'transport_status': 'unvalidated', 'data_origin': run.data_origin}


def prediction_output(row):
    return {**row.snapshot, 'id': row.id, 'status': row.status, 'risk_score': row.risk_score,
            'computed_at': row.computed_at, 'cutoff_end_at': row.cutoff_end_at}


@router.get('/course-runs/{run_id}/prediction')
def saved_prediction(run_id: UUID, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run, enrollment = student_enrollment(db, run_id, context)
    base = base_output(run)
    if utcnow() < base['cutoff_end_at']:
        return {**base, 'status': 'not_ready'}
    row = db.scalar(select(Prediction).where(Prediction.enrollment_id == enrollment.id,
        Prediction.cutoff_end_at == base['cutoff_end_at']).order_by(Prediction.computed_at.desc(), Prediction.id.desc()).limit(1))
    return prediction_output(row) if row else {**base, 'status': 'not_computed'}


@router.post('/course-runs/{run_id}/predictions')
def compute_prediction(run_id: UUID, body: EmptyInput = EmptyInput(), context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run, enrollment = student_enrollment(db, run_id, context)
    lock_enrollment(db, run, enrollment)
    run, enrollment = student_enrollment(db, run_id, context)
    base = base_output(run)
    if utcnow() < base['cutoff_end_at']:
        return {**base, 'status': 'not_ready'}
    try:
        metadata, model, background = load_artifact(get_settings().model_artifact_path)
        db.execute(insert(ModelVersion).values(id=uuid.uuid4(), code=metadata['code'],
            artifact_sha256=metadata['artifact_sha256'], metadata_snapshot=metadata).on_conflict_do_nothing(index_elements=['code']))
        version = db.scalar(select(ModelVersion).where(ModelVersion.code == metadata['code']))
        if version.artifact_sha256 != metadata['artifact_sha256'] or version.metadata_snapshot != metadata:
            raise ArtifactUnavailable()
        cached = db.scalar(select(Prediction).where(Prediction.enrollment_id == enrollment.id,
            Prediction.model_version_id == version.id, Prediction.cutoff_end_at == base['cutoff_end_at']))
        if cached:
            return prediction_output(cached)
        features = studyhub_features(db, run, enrollment)
        score, explanation = None, None
        if features['material_interactions']:
            try:
                score, explanation = predict_explain(model, background, features, metadata['feature_order'])
            except (ValueError, RuntimeError, KeyError, TypeError) as error:
                raise ArtifactUnavailable() from error
    except ArtifactUnavailable:
        db.rollback()
        raise ApiError(503, 'MODEL_UNAVAILABLE', 'Mô hình chưa được cài đặt hoặc artifact không tương thích.', {**base, 'cutoff_end_at': base['cutoff_end_at'].isoformat(), 'status': 'model_unavailable'})
    snapshot = {**base, 'risk_score': score, 'cutoff_end_at': base['cutoff_end_at'].isoformat(), 'model_code': version.code,
        'feature_snapshot': features, 'feature_schema_version': metadata['feature_schema_version'],
        'feature_set': metadata['feature_set'], 'threshold': metadata['threshold'],
        'threshold_exceeded': score >= metadata['threshold'] if score is not None else None,
        'calibration_status': metadata['calibration_status'], 'explanation': explanation,
        'artifact_sha256': metadata['artifact_sha256']}
    row = Prediction(enrollment_id=enrollment.id, model_version_id=version.id,
        cutoff_end_at=base['cutoff_end_at'], status='ok' if score is not None else 'insufficient_data',
        risk_score=score, snapshot=snapshot, computed_at=utcnow())
    db.add(row)
    db.commit()
    return prediction_output(row)
