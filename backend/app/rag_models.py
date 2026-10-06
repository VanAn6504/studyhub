"""Page-bound corpus and idempotent chat turns; source text stays immutable."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class DocumentChunk(Base):
    __tablename__ = 'document_chunks'
    __table_args__ = (
        UniqueConstraint('document_version_id', 'pdf_page', 'chunk_index'),
        CheckConstraint('pdf_page BETWEEN 1 AND 500 AND chunk_index >= 0 AND revision >= 1'),
        CheckConstraint("review_status IN ('pending','reviewed','rejected')"),
        CheckConstraint("kind IN ('content','cover','toc','image')"),
        CheckConstraint("extraction_method IN ('pypdf','manual')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('document_versions.id'), nullable=False, index=True)
    pdf_page: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSONB)
    embedding_code: Mapped[str | None] = mapped_column(Text)
    auto_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    flags: Mapped[list] = mapped_column(JSONB, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default='content')
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default='pending', index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagPreparation(Base):
    __tablename__ = 'rag_preparations'
    __table_args__ = (CheckConstraint("status IN ('unprepared','processing','ready','needs_review','failed')"),)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('document_versions.id'), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default='unprepared')
    authorized_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)


class ChatSession(Base):
    __tablename__ = 'chat_sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('enrollments.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatTurn(Base):
    __tablename__ = 'chat_turns'
    __table_args__ = (
        UniqueConstraint('chat_session_id', 'request_key'),
        CheckConstraint("status IN ('pending','answered','insufficient_sources','provider_error')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    chat_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('chat_sessions.id'), nullable=False, index=True)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model_code: Mapped[str | None] = mapped_column(Text)
    generation_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
