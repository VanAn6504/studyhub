"""Add public metadata, opt-in admissions and private account/resume data."""
import re
import unicodedata

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0009_website_p0'
down_revision = '0008_permanent_documents'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=False, server_default=''))
    for column in (
        sa.Column('enrollment_mode', sa.Text(), nullable=False, server_default='invite_only'),
        sa.Column('listed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('opens_at', sa.DateTime(timezone=True)), sa.Column('closes_at', sa.DateTime(timezone=True)),
        sa.Column('capacity', sa.Integer()), sa.Column('admissions_revision', sa.Integer(), nullable=False, server_default='1'),
    ):
        op.add_column('course_runs', column)
    op.create_check_constraint('ck_admissions_mode', 'course_runs', "enrollment_mode IN ('invite_only','approval','open')")
    op.create_check_constraint('ck_admissions_capacity', 'course_runs', 'capacity IS NULL OR capacity>=1')
    op.create_check_constraint('ck_admissions_window', 'course_runs', 'opens_at IS NULL OR closes_at IS NULL OR opens_at<closes_at')
    op.create_check_constraint('ck_admissions_revision', 'course_runs', 'admissions_revision>=1')
    op.create_table('categories', sa.Column('code', sa.Text(), primary_key=True), sa.Column('name', sa.Text(), nullable=False), sa.Column('order_index', sa.Integer(), nullable=False, server_default='1'))
    category = sa.table('categories', sa.column('code'), sa.column('name'), sa.column('order_index'))
    op.bulk_insert(category, [{'code':'information-technology','name':'Công nghệ thông tin','order_index':1}, {'code':'data-science','name':'Khoa học dữ liệu','order_index':2}, {'code':'general','name':'Kiến thức chung','order_index':3}])
    op.create_table('course_publications', sa.Column('course_id', UUID(), sa.ForeignKey('courses.id'), primary_key=True), sa.Column('slug', sa.Text(), nullable=False, unique=True), sa.Column('status', sa.Text(), nullable=False, server_default='hidden'), sa.Column('draft', JSONB(), nullable=False), sa.Column('snapshot', JSONB()), sa.Column('category_code', sa.Text(), sa.ForeignKey('categories.code')), sa.Column('search_text', sa.Text(), nullable=False, server_default=''), sa.Column('sort_title', sa.Text(), nullable=False, server_default=''), sa.Column('published_at', sa.DateTime(timezone=True)), sa.CheckConstraint("status IN ('hidden','published')"))
    op.create_index('ix_publications_catalog', 'course_publications', ['status','published_at'])
    publication = sa.table('course_publications', sa.column('course_id', UUID()), sa.column('slug'), sa.column('draft', JSONB()))
    rows = []
    for course in op.get_bind().execute(sa.text('SELECT id,code,title FROM courses')):
        slug = re.sub('[^a-z0-9-]+', '-', course.code.lower()).strip('-') + '-' + str(course.id)[:8]
        rows.append({'course_id':course.id,'slug':slug,'draft':{'title':course.title,'summary':'','description':'','category_code':None,'level':'unspecified','objectives':[],'prerequisites':[],'outline':[],'material_titles':[]}})
    if rows:
        op.bulk_insert(publication, rows)
    op.create_table('enrollment_requests', sa.Column('id', UUID(), primary_key=True), sa.Column('run_id', UUID(), sa.ForeignKey('course_runs.id'), nullable=False), sa.Column('student_id', UUID(), sa.ForeignKey('users.id'), nullable=False), sa.Column('status', sa.Text(), nullable=False, server_default='pending'), sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column('decided_at', sa.DateTime(timezone=True)), sa.Column('decided_by', UUID(), sa.ForeignKey('users.id')), sa.Column('reason', sa.Text(), nullable=False, server_default=''), sa.CheckConstraint("status IN ('pending','approved','rejected','cancelled')"))
    op.create_index('uq_request_pending', 'enrollment_requests', ['run_id','student_id'], unique=True, postgresql_where=sa.text("status='pending'"))
    op.create_index('ix_request_student', 'enrollment_requests', ['student_id','requested_at'])
    op.create_table('learning_resumes', sa.Column('user_id', UUID(), sa.ForeignKey('users.id'), primary_key=True), sa.Column('run_id', UUID(), sa.ForeignKey('course_runs.id'), primary_key=True), sa.Column('topic_id', UUID(), sa.ForeignKey('topics.id', ondelete='SET NULL')), sa.Column('document_version_id', UUID(), sa.ForeignKey('document_versions.id', ondelete='SET NULL')), sa.Column('view', sa.Text(), nullable=False, server_default='topic'), sa.Column('page', sa.Integer(), nullable=False, server_default='1'), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.CheckConstraint("view IN ('topic','pdf','quiz','progress','results') AND page>=1 AND page<=500"))


def downgrade():
    op.drop_table('learning_resumes')
    op.drop_table('enrollment_requests')
    op.drop_table('course_publications')
    op.drop_table('categories')
    for constraint in ('ck_admissions_mode','ck_admissions_capacity','ck_admissions_window','ck_admissions_revision'):
        op.drop_constraint(constraint, 'course_runs', type_='check')
    for name in ('admissions_revision','capacity','closes_at','opens_at','listed','enrollment_mode'):
        op.drop_column('course_runs', name)
    op.drop_column('users', 'bio')
