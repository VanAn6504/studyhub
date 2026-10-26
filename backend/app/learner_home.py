"""Overview and resume use real learning records; resume never writes AI events."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admissions import locked_run, require_student
from app.catalog import fold
from app.courses import Limit, Offset
from app.db import get_db
from app.errors import ApiError
from app.learning_models import QuizAttempt, QuizItem, QuizVersion
from app.models import Course, CourseRun, Enrollment, Topic
from app.quizzes import student_enrollment
from app.resources import version_access
from app.security import AuthContext, utcnow
from app.website_models import CoursePublication, EnrollmentRequest, LearningResume
from app.website_schemas import ResumeInput, ResumeOutput

router = APIRouter(prefix='/me', tags=['learner overview'])


def progress(db, run, enrollment):
    topics = db.scalars(select(Topic).where(Topic.course_id == run.course_id).order_by(Topic.order_index,Topic.id)).all()
    mastered, assessed, review = 0, 0, []
    for topic in topics:
        quiz = db.scalar(select(QuizVersion).where(QuizVersion.topic_id == topic.id, QuizVersion.status == 'published'))
        if not quiz:
            continue
        items = db.scalars(select(QuizItem.id).where(QuizItem.quiz_version_id == quiz.id)).all()
        if len(items) < quiz.min_questions:
            continue
        assessed += 1
        attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.enrollment_id == enrollment.id, QuizAttempt.quiz_version_id == quiz.id, QuizAttempt.status == 'completed').order_by(QuizAttempt.graded_at.desc(), QuizAttempt.id.desc()).limit(1))
        if attempt and attempt.total_questions:
            if attempt.correct_count * 100 >= quiz.pass_percent * attempt.total_questions:
                mastered += 1
            else:
                review.append(dict(topic_id=topic.id,code=topic.code,title=topic.title,run_id=run.id,course_id=run.course_id))
    return dict(mastered=mastered, available=assessed, percent=round(100*mastered/assessed,1) if assessed else None), review


def validated_resume(db, row, run, course):
    topic_id, version_id, view, page, notice = row.topic_id if row else None, row.document_version_id if row else None, row.view if row else 'topic', row.page if row else 1, None
    topic = db.get(Topic, topic_id) if topic_id else None
    if topic_id and (not topic or topic.course_id != course.id):
        topic_id, view, version_id, page = None, 'topic', None, 1
        notice = 'Chủ đề trước không còn khả dụng. Bạn đã được đưa về nội dung học phần.'
    if view == 'pdf':
        try:
            if not version_id:
                raise ApiError(404,'SOURCE_UNAVAILABLE','Nguồn không còn khả dụng.')
            version_access(db, version_id, course.id, published=True)
        except ApiError:
            version_id, view, page = None, 'topic', 1
            notice = 'PDF trước đã thay đổi hoặc bị thu hồi. Bạn đã được đưa về chủ đề để chọn tài liệu hiện tại.'
    if view == 'quiz' and (not topic_id or not db.scalar(select(QuizVersion.id).where(QuizVersion.topic_id == topic_id, QuizVersion.status == 'published'))):
        view, notice = 'topic', 'Quiz trước chưa còn được công bố. Hãy xem lại chủ đề.'
    return ResumeOutput(run_id=run.id,course_id=course.id,course_title=course.title,run_code=run.code,topic_id=topic_id,document_version_id=version_id,view=view,page=page,updated_at=row.updated_at if row else None,notice=notice)


def latest_resume(db, user_id, run_id=None):
    query = select(LearningResume, CourseRun, Course).join(CourseRun, CourseRun.id == LearningResume.run_id).join(Course, Course.id == CourseRun.course_id).join(Enrollment, Enrollment.course_run_id == CourseRun.id).where(LearningResume.user_id == user_id, Enrollment.student_id == user_id, Enrollment.status == 'active')
    if run_id:
        query = query.where(CourseRun.id == run_id)
    row = db.execute(query.order_by(LearningResume.updated_at.desc(),LearningResume.run_id).limit(1)).first()
    return validated_resume(db,*row) if row else None


@router.get('/resume')
def get_resume(run_id: UUID | None = None, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    if run_id:
        student_enrollment(db, run_id, context)
    return {'resume':latest_resume(db,context.user.id,run_id)}


@router.put('/resume', response_model=ResumeOutput)
def save_resume(body: ResumeInput, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    student_enrollment(db, body.run_id, context)
    run, course = locked_run(db, body.run_id)
    student_enrollment(db, body.run_id, context)
    if body.topic_id:
        topic = db.get(Topic, body.topic_id)
        if not topic or topic.course_id != course.id:
            raise ApiError(422, 'RESUME_TOPIC_INVALID', 'Chủ đề không thuộc lớp này.')
    if body.view in ('topic','quiz') and not body.topic_id:
        raise ApiError(422, 'RESUME_TOPIC_REQUIRED', 'Cần chủ đề cho vị trí này.')
    if body.view == 'pdf':
        if not body.document_version_id:
            raise ApiError(422, 'RESUME_PDF_REQUIRED', 'Cần phiên bản PDF cho vị trí này.')
        version, _ = version_access(db, body.document_version_id, course.id, published=True)
        if body.page > version.page_count:
            raise ApiError(422, 'PDF_PAGE_INVALID', 'Trang vượt giới hạn PDF.')
    elif body.document_version_id is not None or body.page != 1:
        raise ApiError(422, 'RESUME_POSITION_INVALID', 'Chỉ vị trí PDF có phiên bản và số trang.')
    row = db.get(LearningResume, (context.user.id, run.id))
    if not row:
        row = LearningResume(user_id=context.user.id,run_id=run.id)
        db.add(row)
    for key,value in body.model_dump(exclude={'run_id'}).items():
        setattr(row,key,value)
    row.updated_at = utcnow()
    db.commit()
    return validated_resume(db,row,run,course)


def personal_courses(db, user_id, q='', status='all'):
    rows = db.execute(select(Enrollment,CourseRun,Course).join(CourseRun,CourseRun.id==Enrollment.course_run_id).join(Course,Course.id==CourseRun.course_id).where(Enrollment.student_id==user_id).order_by(CourseRun.created_at.desc(),CourseRun.id)).all()
    result, review = [], []
    for enrollment,run,course in rows:
        if q and fold(q) not in fold(course.title+' '+course.code+' '+run.code):
            continue
        if status == 'inactive' and enrollment.status != 'inactive':
            continue
        if status == 'learning' and (enrollment.status != 'active' or run.status == 'closed'):
            continue
        if status == 'closed' and (enrollment.status != 'active' or run.status != 'closed'):
            continue
        state, weak = progress(db,run,enrollment) if enrollment.status == 'active' else (None,[])
        review.extend(weak)
        publication = db.get(CoursePublication,course.id)
        result.append(dict(course_id=course.id,course_title=course.title,course_code=course.code,run_id=run.id,run_code=run.code,run_status=run.status,data_origin=run.data_origin,enrollment_status=enrollment.status,progress=state,slug=publication.slug if publication and publication.status=='published' else None,resume=latest_resume(db,user_id,run.id) if enrollment.status=='active' else None))
    return result, review


@router.get('/courses')
def my_courses(q: Annotated[str, Query(max_length=160)] = '', status: Literal['all','learning','closed','inactive'] = 'all', limit: Limit = 12, offset: Offset = 0, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    rows,_ = personal_courses(db,context.user.id,q,status)
    return dict(items=rows[offset:offset+limit],total=len(rows),limit=limit,offset=offset)


@router.get('/overview')
def overview(context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    rows,review = personal_courses(db,context.user.id)
    pending = db.scalars(select(EnrollmentRequest).where(EnrollmentRequest.student_id==context.user.id,EnrollmentRequest.status=='pending').order_by(EnrollmentRequest.requested_at.desc()).limit(5)).all()
    from app.admissions import request_output
    return dict(resume=latest_resume(db,context.user.id),courses=[r for r in rows if r['enrollment_status']=='active'][:4],review_topics=review[:6],pending_requests=[request_output(db,r) for r in pending],total_classes=len(rows))
