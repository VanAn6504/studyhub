"""Document opt-in and automatic eligibility; preserve existing human reviews."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0006_rag_workflow'
down_revision = '0005_embeddings'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('document_chunks', sa.Column('auto_eligible', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('rag_preparations',
        sa.Column('document_version_id', UUID, sa.ForeignKey('document_versions.id'), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('authorized_by', UUID, sa.ForeignKey('users.id')),
        sa.Column('authorized_at', sa.DateTime(timezone=True)),
        sa.Column('generation_id', UUID),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('error_code', sa.Text()),
        sa.CheckConstraint("status IN ('unprepared','processing','ready','needs_review','failed')"))


def downgrade():
    op.drop_table('rag_preparations')
    op.drop_column('document_chunks', 'auto_eligible')
