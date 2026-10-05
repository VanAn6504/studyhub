"""Versioned PDFs, quizzes, attempts and learning events. Static PostgreSQL DDL snapshot."""
from alembic import op

revision = "0002_learning"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

DDL = (
    """CREATE TABLE documents (
    id UUID NOT NULL, 
    course_id UUID NOT NULL, 
    code TEXT NOT NULL, 
    title TEXT NOT NULL, 
    status TEXT DEFAULT 'draft' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (course_id, code), 
    CHECK (status IN ('draft','published','archived')), 
    FOREIGN KEY(course_id) REFERENCES courses (id)
)""",
    """CREATE INDEX ix_documents_course_id ON documents (course_id)""",
    """CREATE TABLE document_versions (
    id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    version INTEGER NOT NULL, 
    storage_key TEXT NOT NULL, 
    original_filename TEXT NOT NULL, 
    sha256 TEXT NOT NULL, 
    page_count INTEGER NOT NULL, 
    byte_size INTEGER NOT NULL, 
    status TEXT DEFAULT 'ready' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (document_id, version), 
    CHECK (version >= 1 AND page_count BETWEEN 1 AND 500 AND byte_size BETWEEN 1 AND 20971520), 
    FOREIGN KEY(document_id) REFERENCES documents (id), 
    UNIQUE (storage_key)
)""",
    """CREATE TABLE questions (
    id UUID NOT NULL, 
    topic_id UUID NOT NULL, 
    code TEXT NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (topic_id, code), 
    FOREIGN KEY(topic_id) REFERENCES topics (id)
)""",
    """CREATE TABLE quiz_versions (
    id UUID NOT NULL, 
    topic_id UUID NOT NULL, 
    version INTEGER NOT NULL, 
    status TEXT DEFAULT 'draft' NOT NULL, 
    pass_percent INTEGER DEFAULT '70' NOT NULL, 
    min_questions INTEGER DEFAULT '3' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    published_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (topic_id, version), 
    CHECK (version >= 1 AND status IN ('draft','published','retired') AND pass_percent BETWEEN 1 AND 100 AND min_questions >= 1), 
    FOREIGN KEY(topic_id) REFERENCES topics (id)
)""",
    """CREATE UNIQUE INDEX uq_quiz_current ON quiz_versions (topic_id) WHERE status = 'published'""",
    """CREATE TABLE learning_events (
    id UUID NOT NULL, 
    enrollment_id UUID NOT NULL, 
    client_event_id UUID NOT NULL, 
    viewer_session_id UUID NOT NULL, 
    type TEXT NOT NULL, 
    document_version_id UUID NOT NULL, 
    pdf_page INTEGER, 
    schema_version TEXT DEFAULT 'learning_event_v1' NOT NULL, 
    client_observed_at TIMESTAMP WITH TIME ZONE, 
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    data_origin TEXT NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (enrollment_id, client_event_id), 
    CHECK (type IN ('document_open','page_view') AND data_origin IN ('real','synthetic')), 
    CHECK ((type = 'document_open' AND pdf_page IS NULL) OR (type = 'page_view' AND pdf_page >= 1)), 
    FOREIGN KEY(enrollment_id) REFERENCES enrollments (id), 
    FOREIGN KEY(document_version_id) REFERENCES document_versions (id)
)""",
    """CREATE INDEX ix_learning_events_features ON learning_events (enrollment_id, occurred_at)""",
    """CREATE TABLE question_versions (
    id UUID NOT NULL, 
    question_id UUID NOT NULL, 
    version INTEGER NOT NULL, 
    stem TEXT NOT NULL, 
    options JSONB NOT NULL, 
    correct_option TEXT NOT NULL, 
    explanation TEXT NOT NULL, 
    sources JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (question_id, version), 
    CHECK (version >= 1 AND correct_option IN ('A','B','C','D')), 
    FOREIGN KEY(question_id) REFERENCES questions (id)
)""",
    """CREATE TABLE quiz_attempts (
    id UUID NOT NULL, 
    enrollment_id UUID NOT NULL, 
    quiz_version_id UUID NOT NULL, 
    status TEXT DEFAULT 'in_progress' NOT NULL, 
    answer_revision INTEGER DEFAULT '0' NOT NULL, 
    answers JSONB DEFAULT '{}' NOT NULL, 
    correct_count INTEGER, 
    total_questions INTEGER, 
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    graded_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CHECK (status IN ('in_progress','completed') AND answer_revision >= 0), 
    CHECK (correct_count IS NULL OR (correct_count BETWEEN 0 AND total_questions AND total_questions >= 1)), 
    FOREIGN KEY(enrollment_id) REFERENCES enrollments (id), 
    FOREIGN KEY(quiz_version_id) REFERENCES quiz_versions (id)
)""",
    """CREATE INDEX ix_quiz_attempts_enrollment_id ON quiz_attempts (enrollment_id)""",
    """CREATE UNIQUE INDEX uq_attempt_in_progress ON quiz_attempts (enrollment_id, quiz_version_id) WHERE status = 'in_progress'""",
    """CREATE TABLE topic_materials (
    topic_id UUID NOT NULL, 
    order_index INTEGER NOT NULL, 
    document_version_id UUID NOT NULL, 
    page_start INTEGER NOT NULL, 
    page_end INTEGER NOT NULL, 
    PRIMARY KEY (topic_id, order_index), 
    CHECK (page_start >= 1 AND page_end >= page_start AND order_index >= 1), 
    FOREIGN KEY(topic_id) REFERENCES topics (id), 
    FOREIGN KEY(document_version_id) REFERENCES document_versions (id)
)""",
    """CREATE TABLE attempt_requests (
    enrollment_id UUID NOT NULL, 
    request_key UUID NOT NULL, 
    attempt_id UUID NOT NULL, 
    PRIMARY KEY (enrollment_id, request_key), 
    FOREIGN KEY(enrollment_id) REFERENCES enrollments (id), 
    FOREIGN KEY(attempt_id) REFERENCES quiz_attempts (id)
)""",
    """CREATE TABLE quiz_version_items (
    id UUID NOT NULL, 
    quiz_version_id UUID NOT NULL, 
    question_version_id UUID NOT NULL, 
    order_index INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (quiz_version_id, order_index), 
    UNIQUE (quiz_version_id, question_version_id), 
    CHECK (order_index >= 1), 
    FOREIGN KEY(quiz_version_id) REFERENCES quiz_versions (id), 
    FOREIGN KEY(question_version_id) REFERENCES question_versions (id)
)""",
)


def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    op.drop_table('quiz_version_items')
    op.drop_table('attempt_requests')
    op.drop_table('topic_materials')
    op.drop_table('quiz_attempts')
    op.drop_table('question_versions')
    op.drop_table('learning_events')
    op.drop_table('quiz_versions')
    op.drop_table('questions')
    op.drop_table('document_versions')
    op.drop_table('documents')
