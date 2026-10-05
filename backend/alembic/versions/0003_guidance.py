"""Immutable learning path and prediction snapshots; preserves existing records."""
from alembic import op
import sqlalchemy as sa

revision = '0003_guidance'
down_revision = '0002_learning'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE learning_paths (
        id UUID PRIMARY KEY, enrollment_id UUID NOT NULL REFERENCES enrollments(id),
        revision INTEGER NOT NULL, input_hash TEXT NOT NULL, snapshot JSONB NOT NULL,
        generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(enrollment_id, revision), UNIQUE(enrollment_id, input_hash))''')
    op.execute('''CREATE TABLE model_versions (
        id UUID PRIMARY KEY, code TEXT NOT NULL UNIQUE, artifact_sha256 TEXT NOT NULL,
        metadata_snapshot JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    op.execute('''CREATE TABLE predictions (
        id UUID PRIMARY KEY, enrollment_id UUID NOT NULL REFERENCES enrollments(id),
        model_version_id UUID NOT NULL REFERENCES model_versions(id), cutoff_end_at TIMESTAMPTZ NOT NULL,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT now(), status TEXT NOT NULL, risk_score DOUBLE PRECISION,
        snapshot JSONB NOT NULL, UNIQUE(enrollment_id, model_version_id, cutoff_end_at),
        CHECK(status IN ('ok','insufficient_data')),
        CHECK((status = 'ok' AND risk_score IS NOT NULL AND risk_score BETWEEN 0 AND 1)
              OR (status = 'insufficient_data' AND risk_score IS NULL)))''')
    op.add_column('quiz_attempts', sa.Column('path_revision', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('quiz_attempts', 'path_revision')
    op.drop_table('predictions')
    op.drop_table('model_versions')
    op.drop_table('learning_paths')
