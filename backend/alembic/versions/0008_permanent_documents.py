"""Delete documents while preserving version identities used by learning logs."""
from alembic import op
import sqlalchemy as sa

revision = '0008_permanent_documents'
down_revision = '0007_document_trash'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('document_versions_document_id_fkey', 'document_versions', type_='foreignkey')
    op.alter_column('document_versions', 'document_id', nullable=True)
    op.create_foreign_key('document_versions_document_id_fkey', 'document_versions', 'documents', ['document_id'], ['id'], ondelete='SET NULL')
    op.create_table('pdf_file_deletions', sa.Column('storage_key', sa.Text(), primary_key=True))


def downgrade():
    # Historical version identities cannot be assigned back to deleted documents.
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT count(*) FROM document_versions WHERE document_id IS NULL')):
        raise RuntimeError('Cannot downgrade after permanent document deletion; restore a database/PDF backup together.')
    if connection.scalar(sa.text('SELECT count(*) FROM pdf_file_deletions')):
        raise RuntimeError('Pending PDF file deletions must be completed before downgrade.')
    op.drop_table('pdf_file_deletions')
    op.drop_constraint('document_versions_document_id_fkey', 'document_versions', type_='foreignkey')
    op.alter_column('document_versions', 'document_id', nullable=False)
    op.create_foreign_key('document_versions_document_id_fkey', 'document_versions', 'documents', ['document_id'], ['id'])
