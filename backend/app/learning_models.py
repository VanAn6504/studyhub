"""Versioned learning resources and server-owned learning records."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("course_id", "code"), CheckConstraint("status IN ('draft','published','archived')"))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version"), CheckConstraint("version >= 1 AND page_count BETWEEN 1 AND 500 AND byte_size BETWEEN 1 AND 20971520"))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TopicMaterial(Base):
    __tablename__ = "topic_materials"
    __table_args__ = (CheckConstraint("page_start >= 1 AND page_end >= page_start AND order_index >= 1"),)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("topic_id", "code"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)


class QuestionVersion(Base):
    __tablename__ = "question_versions"
    __table_args__ = (UniqueConstraint("question_id", "version"), CheckConstraint("version >= 1 AND correct_option IN ('A','B','C','D')"))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False)
    correct_option: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuizVersion(Base):
    __tablename__ = "quiz_versions"
    __table_args__ = (UniqueConstraint("topic_id", "version"), CheckConstraint("version >= 1 AND status IN ('draft','published','retired') AND pass_percent BETWEEN 1 AND 100 AND min_questions >= 1"), Index("uq_quiz_current", "topic_id", unique=True, postgresql_where=text("status = 'published'")))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    pass_percent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="70")
    min_questions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuizItem(Base):
    __tablename__ = "quiz_version_items"
    __table_args__ = (UniqueConstraint("quiz_version_id", "order_index"), UniqueConstraint("quiz_version_id", "question_version_id"), CheckConstraint("order_index >= 1"))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    quiz_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_versions.id"), nullable=False)
    question_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_versions.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (CheckConstraint("status IN ('in_progress','completed') AND answer_revision >= 0"), CheckConstraint("correct_count IS NULL OR (correct_count BETWEEN 0 AND total_questions AND total_questions >= 1)"), Index("uq_attempt_in_progress", "enrollment_id", "quiz_version_id", unique=True, postgresql_where=text("status = 'in_progress'")))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), nullable=False, index=True)
    quiz_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_versions.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="in_progress")
    answer_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    correct_count: Mapped[int | None] = mapped_column(Integer)
    total_questions: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    path_revision: Mapped[int | None] = mapped_column(Integer)


class AttemptRequest(Base):
    __tablename__ = "attempt_requests"
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), primary_key=True)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_attempts.id"), nullable=False)


class LearningEvent(Base):
    __tablename__ = "learning_events"
    __table_args__ = (UniqueConstraint("enrollment_id", "client_event_id"), CheckConstraint("type IN ('document_open','page_view') AND data_origin IN ('real','synthetic')"), CheckConstraint("(type = 'document_open' AND pdf_page IS NULL) OR (type = 'page_view' AND pdf_page >= 1)"), Index("ix_learning_events_features", "enrollment_id", "occurred_at"))
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), nullable=False)
    client_event_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    viewer_session_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    pdf_page: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="learning_event_v1")
    client_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_origin: Mapped[str] = mapped_column(Text, nullable=False)
