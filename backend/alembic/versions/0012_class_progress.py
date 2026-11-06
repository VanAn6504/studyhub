"""Per-class quiz deadlines and durable identity for activity aggregates."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0012_class_progress'
down_revision = '0011_rag_jobs'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('document_versions', sa.Column('learning_document_id', UUID()))
    op.execute('UPDATE document_versions SET learning_document_id = document_id WHERE document_id IS NOT NULL')
    op.create_table('class_quiz_deadlines',
        sa.Column('course_run_id', UUID(), sa.ForeignKey('course_runs.id'), primary_key=True),
        sa.Column('quiz_version_id', UUID(), sa.ForeignKey('quiz_versions.id'), primary_key=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(timezone=True)))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM class_quiz_deadlines)')):
        raise RuntimeError('Back up and migrate class deadlines before downgrading.')
    op.drop_table('class_quiz_deadlines')
    op.drop_column('document_versions', 'learning_document_id')
