"""Users, revocable sessions, courses, runs, enrollments and topic DAG.

Revision ID: 0001_foundation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('teacher','student')", name="ck_users_role"),
        sa.CheckConstraint("email = lower(btrim(email))", name="ck_users_normalized_email"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "courses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("owner_teacher_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("content_revision >= 1", name="ck_courses_revision"),
    )
    op.create_index("ix_courses_owner_teacher_id", "courses", ["owner_teacher_id"])
    op.create_table(
        "course_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("course_id", UUID, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("course_run_start_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="Asia/Bangkok"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("data_origin", sa.Text(), nullable=False, server_default="real"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("course_id", "code", name="uq_course_runs_course_code"),
        sa.CheckConstraint("status IN ('draft','active','closed')", name="ck_course_runs_status"),
        sa.CheckConstraint("data_origin IN ('real','synthetic')", name="ck_course_runs_origin"),
    )
    op.create_table(
        "enrollments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("course_run_id", UUID, sa.ForeignKey("course_runs.id"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("course_run_id", "student_id", name="uq_enrollments_run_student"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_enrollments_status"),
    )
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_table(
        "topics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("course_id", UUID, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("objectives", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("course_id", "code", name="uq_topics_course_code"),
        sa.UniqueConstraint("course_id", "order_index", name="uq_topics_course_order"),
        sa.UniqueConstraint("id", "course_id", name="uq_topics_id_course"),
        sa.CheckConstraint("order_index >= 1", name="ck_topics_order"),
        sa.CheckConstraint("jsonb_typeof(objectives) = 'array'", name="ck_topics_objectives_array"),
    )
    op.create_table(
        "topic_prerequisites",
        sa.Column("topic_id", UUID, primary_key=True),
        sa.Column("prerequisite_topic_id", UUID, primary_key=True),
        sa.Column("course_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["topic_id", "course_id"], ["topics.id", "topics.course_id"], name="fk_prerequisites_topic_course"),
        sa.ForeignKeyConstraint(["prerequisite_topic_id", "course_id"], ["topics.id", "topics.course_id"], name="fk_prerequisites_prerequisite_course"),
        sa.CheckConstraint("topic_id <> prerequisite_topic_id", name="ck_prerequisites_not_self"),
    )


def downgrade():
    op.drop_table("topic_prerequisites")
    op.drop_table("topics")
    op.drop_index("ix_enrollments_student_id", table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_table("course_runs")
    op.drop_index("ix_courses_owner_teacher_id", table_name="courses")
    op.drop_table("courses")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
