"""Immutable learning paths and cutoff prediction snapshots."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class LearningPath(Base):
    __tablename__ = 'learning_paths'
    __table_args__ = (UniqueConstraint('enrollment_id', 'revision'), UniqueConstraint('enrollment_id', 'input_hash'))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('enrollments.id'), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelVersion(Base):
    __tablename__ = 'model_versions'
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    artifact_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Prediction(Base):
    __tablename__ = 'predictions'
    __table_args__ = (UniqueConstraint('enrollment_id', 'model_version_id', 'cutoff_end_at'),
                      CheckConstraint("status IN ('ok','insufficient_data')"),
                      CheckConstraint("(status = 'ok' AND risk_score IS NOT NULL AND risk_score BETWEEN 0 AND 1) OR (status = 'insufficient_data' AND risk_score IS NULL)"))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('enrollments.id'), nullable=False)
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('model_versions.id'), nullable=False)
    cutoff_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Float)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
