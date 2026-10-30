"""Website metadata and admission records; never public learning resources."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Category(Base):
    __tablename__ = 'categories'
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default='1')


class CoursePublication(Base):
    __tablename__ = 'course_publications'
    __table_args__ = (CheckConstraint("status IN ('hidden','published')"), Index('ix_publications_catalog', 'status', 'published_at'))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id'), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default='hidden')
    draft: Mapped[dict] = mapped_column(JSONB, nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(JSONB)
    category_code: Mapped[str | None] = mapped_column(ForeignKey('categories.code'))
    search_text: Mapped[str] = mapped_column(Text, nullable=False, server_default='')
    sort_title: Mapped[str] = mapped_column(Text, nullable=False, server_default='')
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EnrollmentRequest(Base):
    __tablename__ = 'enrollment_requests'
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected','cancelled')"),
        Index('uq_request_pending', 'run_id', 'student_id', unique=True, postgresql_where=text("status='pending'")),
        Index('ix_request_student', 'student_id', 'requested_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('course_runs.id'), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default='pending')
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default='')


class LearningResume(Base):
    __tablename__ = 'learning_resumes'
    __table_args__ = (CheckConstraint("view IN ('topic','pdf','quiz','progress','results') AND page>=1 AND page<=2000"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('course_runs.id'), primary_key=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('topics.id', ondelete='SET NULL'))
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('document_versions.id', ondelete='SET NULL'))
    view: Mapped[str] = mapped_column(Text, nullable=False, server_default='topic')
    page: Mapped[int] = mapped_column(Integer, nullable=False, server_default='1')
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
