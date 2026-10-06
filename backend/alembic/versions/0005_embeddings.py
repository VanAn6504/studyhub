"""Persist local pretrained embeddings without changing immutable source text."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0005_embeddings'
down_revision = '0004_rag'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('document_chunks', sa.Column('embedding', JSONB, nullable=True))
    op.add_column('document_chunks', sa.Column('embedding_code', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('document_chunks', 'embedding_code')
    op.drop_column('document_chunks', 'embedding')
