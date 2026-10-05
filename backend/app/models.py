import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('teacher','student')", name="ck_users_role"),
        CheckConstraint("email = lower(btrim(email))", name="ck_users_normalized_email"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (CheckConstraint("content_revision >= 1", name="ck_courses_revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    owner_teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    content_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CourseRun(Base):
    __tablename__ = "course_runs"
    __table_args__ = (
        UniqueConstraint("course_id", "code", name="uq_course_runs_course_code"),
        CheckConstraint("status IN ('draft','active','closed')", name="ck_course_runs_status"),
        CheckConstraint("data_origin IN ('real','synthetic')", name="ck_course_runs_origin"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    course_run_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Bangkok")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    data_origin: Mapped[str] = mapped_column(Text, nullable=False, server_default="real")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_run_id", "student_id", name="uq_enrollments_run_student"),
        CheckConstraint("status IN ('active','inactive')", name="ck_enrollments_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("course_runs.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("course_id", "code", name="uq_topics_course_code"),
        UniqueConstraint("course_id", "order_index", name="uq_topics_course_order"),
        UniqueConstraint("id", "course_id", name="uq_topics_id_course"),
        CheckConstraint("order_index >= 1", name="ck_topics_order"),
        CheckConstraint("jsonb_typeof(objectives) = 'array'", name="ck_topics_objectives_array"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    objectives: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class TopicPrerequisite(Base):
    __tablename__ = "topic_prerequisites"
    __table_args__ = (
        ForeignKeyConstraint(["topic_id", "course_id"], ["topics.id", "topics.course_id"], name="fk_prerequisites_topic_course"),
        ForeignKeyConstraint(["prerequisite_topic_id", "course_id"], ["topics.id", "topics.course_id"], name="fk_prerequisites_prerequisite_course"),
        CheckConstraint("topic_id <> prerequisite_topic_id", name="ck_prerequisites_not_self"),
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    prerequisite_topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


# Register the next module's tables with the same metadata for Alembic.
from app import learning_models  # noqa: E402,F401
from app import guidance_models  # noqa: E402,F401
