"""100MiB/2000pages and independent document classification; preserve old rows."""
from alembic import op
import sqlalchemy as sa

revision='0010_large_pdf'
down_revision='0009_website_p0'
branch_labels=None
depends_on=None

def replace_check(table, marker, name, condition):
    for check in sa.inspect(op.get_bind()).get_check_constraints(table):
        if marker in check['sqltext']:
            op.drop_constraint(check['name'],table,type_='check')
    op.create_check_constraint(name,table,condition)

def limits(pages,byte_size):
    replace_check('document_versions','page_count','ck_pdf_limits',f'version>=1 AND page_count BETWEEN 1 AND {pages} AND byte_size BETWEEN 1 AND {byte_size}')
    replace_check('document_chunks','chunk_index','ck_chunk_position',f'pdf_page BETWEEN 1 AND {pages} AND chunk_index>=0 AND revision>=1')
    replace_check('learning_resumes','page','ck_resume_position',f"view IN ('topic','pdf','quiz','progress','results') AND page>=1 AND page<={pages}")

def upgrade():
    limits(2000,104857600)
    op.add_column('documents',sa.Column('document_type',sa.Text(),nullable=False,server_default='lecture'))
    op.add_column('documents',sa.Column('show_in_learning',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_check_constraint('ck_document_type','documents',"document_type IN ('textbook','lecture','supplement')")

def downgrade():
    connection=op.get_bind()
    if connection.scalar(sa.text('''SELECT EXISTS(SELECT 1 FROM document_versions WHERE page_count>500 OR byte_size>20971520)
        OR EXISTS(SELECT 1 FROM document_chunks WHERE pdf_page>500)
        OR EXISTS(SELECT 1 FROM learning_resumes WHERE page>500)''')):
        raise RuntimeError('Downgrade blocked: PDFs/pages exceed old20MiB/500page limits. Preserve/restore a compatible DB+PDF backup; no data was deleted.')
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM documents WHERE document_type!='lecture' OR NOT show_in_learning)")):
        raise RuntimeError('Downgrade blocked: document classification/display settings would be lost. Export/restore a compatible backup first; no data was deleted.')
    limits(500,20971520)
    op.drop_constraint('ck_document_type','documents',type_='check')
    op.drop_column('documents','show_in_learning')
    op.drop_column('documents','document_type')
