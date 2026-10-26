"""Public metadata only. Publication never grants access to learning resources."""
import re
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.courses import owner_course
from app.db import get_db
from app.errors import ApiError
from app.models import Course, CourseRun, Enrollment, User
from app.schemas import Page
from app.security import AuthContext, require_teacher, utcnow
from app.website_models import Category, CoursePublication
from app.website_schemas import CategoryOutput, PublicCourse, PublicRun, PublicationInput, PublicationOutput

router = APIRouter(prefix='/catalog', tags=['public catalog'])
teaching_router = APIRouter(prefix='/teaching', tags=['course publication'])


def fold(value):
    value = value.casefold().replace('đ', 'd')
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c)).split())


def publication_for(db, course, create=False):
    publication = db.get(CoursePublication, course.id)
    if publication is None:
        publication = CoursePublication(course_id=course.id, slug=re.sub('[^a-z0-9-]+', '-', course.code.lower()).strip('-') + '-' + str(course.id)[:8], status='hidden', draft=PublicationInput(title=course.title).model_dump())
        if create:
            db.add(publication)
    return publication


def publication_output(publication):
    return dict(course_id=publication.course_id, slug=publication.slug, status=publication.status, draft=publication.draft, published=publication.snapshot, published_at=publication.published_at)


def active_count(db, run_id):
    return db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.course_run_id == run_id, Enrollment.status == 'active')) or 0


def availability(run, count, now=None):
    now = now or utcnow()
    if run.status != 'active' or (run.closes_at and now >= run.closes_at):
        return 'closed'
    if run.opens_at and now < run.opens_at:
        return 'not_started'
    if run.enrollment_mode == 'invite_only':
        return 'invite_only'
    if run.capacity is not None and count >= run.capacity:
        return 'full'
    return 'accepting'


def public_output(db, publication, course, teacher):
    category = db.get(Category, publication.category_code) if publication.category_code else None
    runs = []
    for run in db.scalars(select(CourseRun).where(CourseRun.course_id == course.id, CourseRun.listed.is_(True), CourseRun.data_origin == 'real', CourseRun.status.in_(['active', 'closed'])).order_by(CourseRun.course_run_start_date, CourseRun.id)):
        count = active_count(db, run.id)
        runs.append(PublicRun(id=run.id, code=run.code, instructor_name=teacher.display_name, start_date=run.course_run_start_date, timezone=run.timezone, status=run.status, enrollment_mode=run.enrollment_mode, opens_at=run.opens_at, closes_at=run.closes_at, capacity=run.capacity, seats_remaining=max(0, run.capacity-count) if run.capacity else None, availability=availability(run, count), admissions_revision=run.admissions_revision))
    return PublicCourse(**publication.snapshot, slug=publication.slug, code=course.code, category_name=category.name if category else None, instructor_name=teacher.display_name, published_at=publication.published_at, runs=runs)


@router.get('/categories', response_model=list[CategoryOutput])
def categories(db: Session = Depends(get_db)):
    rows = db.execute(select(Category, func.count(CoursePublication.course_id)).join(CoursePublication, CoursePublication.category_code == Category.code).where(CoursePublication.status == 'published').group_by(Category.code).order_by(Category.order_index, Category.code))
    return [dict(code=c.code, name=c.name, course_count=count) for c, count in rows]


@router.get('/courses', response_model=Page[PublicCourse])
def catalog_courses(q: Annotated[str, Query(max_length=160)] = '', category: Annotated[str, Query(max_length=64)] = '', level: Literal['', 'unspecified', 'beginner', 'intermediate', 'advanced'] = '', availability_filter: Annotated[Literal['all', 'accepting'], Query(alias='availability')] = 'all', sort: Literal['relevance', 'newest', 'title'] = 'newest', limit: Annotated[int, Query(ge=1, le=24)] = 12, offset: Annotated[int, Query(ge=0, le=100000)] = 0, db: Session = Depends(get_db)):
    query = select(CoursePublication, Course, User).join(Course, Course.id == CoursePublication.course_id).join(User, User.id == Course.owner_teacher_id).where(CoursePublication.status == 'published', User.is_active.is_(True))
    normalized = fold(q)
    if normalized:
        escaped = normalized.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.where(CoursePublication.search_text.like('%'+escaped+'%', escape='\\'))
    if category:
        query = query.where(CoursePublication.category_code == category)
    if level:
        query = query.where(CoursePublication.snapshot['level'].astext == level)
    if availability_filter == 'accepting':
        count = select(func.count()).select_from(Enrollment).where(Enrollment.course_run_id == CourseRun.id, Enrollment.status == 'active').correlate(CourseRun).scalar_subquery()
        now = utcnow()
        exists = select(CourseRun.id).where(CourseRun.course_id == Course.id, CourseRun.listed.is_(True), CourseRun.data_origin == 'real', CourseRun.status == 'active', CourseRun.enrollment_mode.in_(['open','approval']), (CourseRun.opens_at.is_(None) | (CourseRun.opens_at <= now)), (CourseRun.closes_at.is_(None) | (CourseRun.closes_at > now)), (CourseRun.capacity.is_(None) | (count < CourseRun.capacity))).exists()
        query = query.where(exists)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    order = [CoursePublication.published_at.desc(), Course.id]
    if sort == 'title':
        order = [CoursePublication.sort_title, Course.id]
    elif sort == 'relevance' and normalized:
        order = [case((func.lower(Course.code) == normalized, 0), (CoursePublication.sort_title == normalized, 1), else_=2), CoursePublication.sort_title, Course.id]
    rows = db.execute(query.order_by(*order).limit(limit).offset(offset))
    return dict(items=[public_output(db, p, c, u) for p, c, u in rows], total=total, limit=limit, offset=offset)


@router.get('/courses/{slug}', response_model=PublicCourse)
def course_detail(slug: str, db: Session = Depends(get_db)):
    if len(slug) > 160:
        raise ApiError(404, 'COURSE_NOT_FOUND', 'Không tìm thấy học phần công khai.')
    row = db.execute(select(CoursePublication, Course, User).join(Course, Course.id == CoursePublication.course_id).join(User, User.id == Course.owner_teacher_id).where(CoursePublication.slug == slug, CoursePublication.status == 'published', User.is_active.is_(True))).first()
    if not row:
        raise ApiError(404, 'COURSE_NOT_FOUND', 'Không tìm thấy học phần công khai.')
    return public_output(db, *row)


@teaching_router.get('/categories', response_model=list[CategoryOutput])
def all_categories(context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    return [dict(code=c.code, name=c.name) for c in db.scalars(select(Category).order_by(Category.order_index, Category.code))]


@teaching_router.get('/courses/{course_id}/publication', response_model=PublicationOutput)
def read_publication(course_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    return publication_output(publication_for(db, owner_course(db, course_id, context.user.id)))


@teaching_router.patch('/courses/{course_id}/publication', response_model=PublicationOutput)
def save_publication(course_id: UUID, body: PublicationInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    course = owner_course(db, course_id, context.user.id, lock=True)
    if body.category_code and not db.get(Category, body.category_code):
        raise ApiError(422, 'CATEGORY_INVALID', 'Lĩnh vực không hợp lệ.')
    publication = publication_for(db, course, create=True)
    publication.draft = body.model_dump()
    db.commit()
    return publication_output(publication)


@teaching_router.post('/courses/{course_id}/publish', response_model=PublicationOutput)
def publish(course_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    publication = publication_for(db, owner_course(db, course_id, context.user.id, lock=True), create=True)
    body = PublicationInput.model_validate(publication.draft)
    if not body.summary or not body.description or not body.category_code or not db.get(Category, body.category_code):
        raise ApiError(422, 'PUBLICATION_INCOMPLETE', 'Điền tóm tắt, giới thiệu và lĩnh vực trước khi công bố.')
    publication.snapshot = body.model_dump()
    publication.category_code = body.category_code
    publication.sort_title = fold(body.title)
    course = db.get(Course, course_id)
    publication.search_text = fold(' '.join([course.code, body.title, body.summary, body.description]))
    publication.status, publication.published_at = 'published', utcnow()
    db.commit()
    return publication_output(publication)


@teaching_router.post('/courses/{course_id}/hide', response_model=PublicationOutput)
def hide(course_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    publication = publication_for(db, owner_course(db, course_id, context.user.id, lock=True), create=True)
    publication.status = 'hidden'
    db.commit()
    return publication_output(publication)
