"""Reversible document deletion; retain PDF versions and learning history."""
from alembic import op
import sqlalchemy as sa

revision = '0007_document_trash'
down_revision = '0006_rag_workflow'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('documents', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('documents', 'deleted_at')
