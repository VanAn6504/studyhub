"""Add RAG tables without modifying existing learning data."""
from alembic import op

revision = '0004_rag'
down_revision = '0003_guidance'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE document_chunks (
        id UUID PRIMARY KEY, document_version_id UUID NOT NULL REFERENCES document_versions(id),
        pdf_page INTEGER NOT NULL, chunk_index INTEGER NOT NULL, text TEXT NOT NULL,
        source_hash TEXT NOT NULL, extraction_method TEXT NOT NULL, flags JSONB NOT NULL,
        kind TEXT NOT NULL, review_status TEXT NOT NULL, revision INTEGER NOT NULL,
        reviewed_by UUID REFERENCES users(id), reviewed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(document_version_id,pdf_page,chunk_index),
        CHECK(pdf_page BETWEEN 1 AND 500 AND chunk_index >= 0 AND revision >= 1),
        CHECK(review_status IN ('pending','reviewed','rejected')),
        CHECK(kind IN ('content','cover','toc','image')),
        CHECK(extraction_method IN ('pypdf','manual')))''')
    op.create_index('ix_document_chunks_document_version_id', 'document_chunks', ['document_version_id'])
    op.create_index('ix_document_chunks_review_status', 'document_chunks', ['review_status'])
    op.execute('''CREATE TABLE chat_sessions (
        id UUID PRIMARY KEY, enrollment_id UUID NOT NULL REFERENCES enrollments(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    op.create_index('ix_chat_sessions_enrollment_id', 'chat_sessions', ['enrollment_id'])
    op.execute('''CREATE TABLE chat_turns (
        id UUID PRIMARY KEY, chat_session_id UUID NOT NULL REFERENCES chat_sessions(id),
        request_key UUID NOT NULL, question TEXT NOT NULL, answer TEXT,
        status TEXT NOT NULL, citations JSONB NOT NULL, model_code TEXT,
        generation_id UUID NOT NULL, started_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(chat_session_id,request_key),
        CHECK(status IN ('pending','answered','insufficient_sources','provider_error')))''')
    op.create_index('ix_chat_turns_chat_session_id', 'chat_turns', ['chat_session_id'])


def downgrade():
    op.drop_table('chat_turns')
    op.drop_table('chat_sessions')
    op.drop_table('document_chunks')
