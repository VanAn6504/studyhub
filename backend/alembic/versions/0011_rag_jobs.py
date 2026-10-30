"""Durable page checkpoints/leases and explicit RAG page scopes. No source opt-in."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision='0011_rag_jobs'
down_revision='0010_large_pdf'
branch_labels=None
depends_on=None

def upgrade():
    for check in sa.inspect(op.get_bind()).get_check_constraints('rag_preparations'):
        if 'status' in check['sqltext']:op.drop_constraint(check['name'],'rag_preparations',type_='check')
    op.create_check_constraint('ck_rag_job_status','rag_preparations',"status IN ('unprepared','queued','processing','ready','needs_review','failed','cancelled')")
    for column in (
        sa.Column('scope_ranges',JSONB(),nullable=False,server_default='[]'),
        sa.Column('stage',sa.Text(),nullable=False,server_default='idle'),
        sa.Column('lease_id',UUID()),sa.Column('heartbeat_at',sa.DateTime(timezone=True)),
        sa.Column('queued_at',sa.DateTime(timezone=True)),sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('embedded_chunks',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('embedding_code',sa.Text()),
    ):op.add_column('rag_preparations',column)
    op.create_index('ix_rag_queue','rag_preparations',['status','queued_at'])
    op.create_table('rag_page_checkpoints',
        sa.Column('document_version_id',UUID(),sa.ForeignKey('document_versions.id'),primary_key=True),
        sa.Column('pdf_page',sa.Integer(),primary_key=True),
        sa.Column('extracted',sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column('chunked',sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.CheckConstraint('pdf_page BETWEEN 1 AND 2000',name='ck_rag_checkpoint_page'))
    # Existing extraction is immutable and already complete on pages with chunks.
    op.execute('''INSERT INTO rag_page_checkpoints(document_version_id,pdf_page)
        SELECT DISTINCT document_version_id,pdf_page FROM document_chunks''')
    # An old in-flight FastAPI background task cannot survive a process deployment.
    op.execute("UPDATE rag_preparations SET status='queued',queued_at=now() WHERE enabled AND status='processing'")
    op.add_column('chat_turns',sa.Column('topic_id',UUID(),sa.ForeignKey('topics.id',ondelete='SET NULL')))

def downgrade():
    connection=op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM rag_preparations WHERE status IN ('queued','processing','cancelled') OR scope_ranges!='[]'::jsonb) OR EXISTS(SELECT 1 FROM chat_turns WHERE topic_id IS NOT NULL)")):
        raise RuntimeError('Downgrade blocked: active jobs, scopes or chat context would be lost. Drain/export jobs and restore a compatible backup; no data was deleted.')
    op.drop_column('chat_turns','topic_id')
    op.drop_table('rag_page_checkpoints')
    op.drop_index('ix_rag_queue',table_name='rag_preparations')
    for name in ('scope_ranges','stage','lease_id','heartbeat_at','queued_at','attempts','embedded_chunks','embedding_code'):op.drop_column('rag_preparations',name)
    op.drop_constraint('ck_rag_job_status','rag_preparations',type_='check')
    op.create_check_constraint('ck_rag_job_status','rag_preparations',"status IN ('unprepared','processing','ready','needs_review','failed')")
