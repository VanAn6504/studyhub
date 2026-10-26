"""Admission state machine. Course -> run locks serialize every seat allocation."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import active_count, availability, publication_for
from app.courses import Limit, Offset, owner_run
from app.db import get_db
from app.errors import ApiError
from app.models import Course, CourseRun, Enrollment, User
from app.schemas import EnrollmentOutput
from app.security import AuthContext, get_auth, require_teacher, utcnow
from app.website_models import CoursePublication, EnrollmentRequest
from app.website_schemas import AdmissionsInput, DecisionInput, JoinInput

router = APIRouter(tags=['admissions'])


def require_student(context: AuthContext = Depends(get_auth)):
    if context.user.role != 'student':
        raise ApiError(403, 'ROLE_FORBIDDEN', 'Chức năng này dành cho sinh viên.')
    return context


def locked_run(db, run_id):
    run = db.get(CourseRun, run_id)
    if not run:
        raise ApiError(404, 'RUN_NOT_FOUND', 'Không tìm thấy lớp học.')
    course = db.scalar(select(Course).where(Course.id == run.course_id).with_for_update().execution_options(populate_existing=True))
    run = db.scalar(select(CourseRun).where(CourseRun.id == run_id).with_for_update().execution_options(populate_existing=True))
    return run, course


def existing_enrollment(db, run, student_id):
    enrollment = db.scalar(select(Enrollment).where(Enrollment.course_run_id == run.id, Enrollment.student_id == student_id).execution_options(populate_existing=True))
    if enrollment and enrollment.status == 'inactive':
        raise ApiError(409, 'ENROLLMENT_INACTIVE', 'Đăng ký học đã bị giảng viên vô hiệu. Hãy liên hệ giảng viên để được kích hoạt lại.')
    return enrollment


def assert_capacity(db, run):
    if run.capacity is not None and active_count(db, run.id) >= run.capacity:
        raise ApiError(409, 'RUN_FULL', 'Lớp đã đủ chỗ. Yêu cầu chờ duyệt không giữ chỗ.')


def check_admission(db, run, course, mode, revision=None):
    publication = db.get(CoursePublication, course.id, populate_existing=True)
    teacher = db.get(User, course.owner_teacher_id)
    if not publication or publication.status != 'published' or not teacher.is_active or not run.listed or run.data_origin != 'real':
        raise ApiError(404, 'RUN_NOT_FOUND', 'Lớp không được công khai nhận đăng ký.')
    if revision is not None and revision != run.admissions_revision:
        raise ApiError(409, 'ADMISSIONS_CHANGED', 'Chính sách lớp vừa thay đổi. Tải lại thông tin lớp trước khi xác nhận.')
    if run.enrollment_mode != mode:
        raise ApiError(409, 'ADMISSION_MODE_CHANGED', 'Hình thức tham gia lớp đã thay đổi. Hãy tải lại thông tin.')
    state = availability(run, active_count(db, run.id))
    if state != 'accepting':
        messages = {'full':'Lớp đã đủ chỗ. Yêu cầu chờ duyệt không giữ chỗ.', 'not_started':'Chưa đến thời gian nhận đăng ký.', 'closed':'Lớp đã đóng hoặc hết thời gian nhận đăng ký.'}
        raise ApiError(409, 'RUN_'+state.upper(), messages.get(state, 'Lớp chỉ nhận lời mời của giảng viên.'))


def settings_output(db, run, course):
    return dict(run_id=run.id, course_id=course.id, course_title=course.title, code=run.code, status=run.status, data_origin=run.data_origin, timezone=run.timezone, enrollment_mode=run.enrollment_mode, listed=run.listed, opens_at=run.opens_at, closes_at=run.closes_at, capacity=run.capacity, active_students=active_count(db, run.id), admissions_revision=run.admissions_revision)


@router.get('/teaching/runs/{run_id}/admissions')
def settings(run_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    run, course = owner_run(db, run_id, context.user.id)
    return settings_output(db, run, course)


@router.patch('/teaching/runs/{run_id}/admissions')
def save_settings(run_id: UUID, body: AdmissionsInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    run, course = owner_run(db, run_id, context.user.id, lock=True)
    if run.data_origin != 'real':
        raise ApiError(409, 'RUN_READ_ONLY', 'Không cấu hình tuyển sinh cho lớp mô phỏng.')
    if body.expected_revision != run.admissions_revision:
        raise ApiError(409, 'ADMISSIONS_CHANGED', 'Cấu hình đã thay đổi. Tải lại trước khi lưu.')
    if body.capacity is not None and body.capacity < active_count(db, run.id):
        raise ApiError(409, 'CAPACITY_BELOW_ENROLLMENT', 'Giới hạn chỗ không được nhỏ hơn số sinh viên đang được kích hoạt.')
    values = body.model_dump(exclude={'expected_revision'})
    if any(getattr(run, key) != value for key, value in values.items()):
        for key, value in values.items():
            setattr(run, key, value)
        run.admissions_revision += 1
        db.commit()
    return settings_output(db, run, course)


@router.post('/course-runs/{run_id}/join', response_model=EnrollmentOutput, status_code=201)
def join(run_id: UUID, body: JoinInput, response: Response, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    run, course = locked_run(db, run_id)
    existing = existing_enrollment(db, run, context.user.id)
    if existing:
        response.status_code = 200
        return existing
    check_admission(db, run, course, 'open', body.expected_revision)
    enrollment = Enrollment(course_run_id=run.id, student_id=context.user.id, status='active')
    db.add(enrollment)
    pending = db.scalar(select(EnrollmentRequest).where(EnrollmentRequest.run_id == run.id, EnrollmentRequest.student_id == context.user.id, EnrollmentRequest.status == 'pending'))
    if pending:
        pending.status, pending.decided_at, pending.decided_by, pending.reason = 'cancelled', utcnow(), context.user.id, 'Đã tham gia khi lớp chuyển sang chế độ mở.'
    db.commit()
    return enrollment


def request_output(db, row, owner=False):
    run, course = db.get(CourseRun, row.run_id), None
    course = db.get(Course, run.course_id)
    publication = db.get(CoursePublication, course.id)
    result = dict(id=row.id, run_id=run.id, run_code=run.code, course_id=course.id, course_title=course.title, slug=publication.slug if publication and publication.status == 'published' else None, status=row.status, requested_at=row.requested_at, decided_at=row.decided_at, reason=row.reason, admissions_revision=run.admissions_revision)
    if owner:
        student = db.get(User, row.student_id)
        result.update(student_name=student.display_name, student_email=student.email)
    return result


@router.post('/course-runs/{run_id}/enrollment-requests', status_code=201)
def request_enrollment(run_id: UUID, body: JoinInput, response: Response, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    run, course = locked_run(db, run_id)
    if existing_enrollment(db, run, context.user.id):
        raise ApiError(409, 'ALREADY_ENROLLED', 'Bạn đã là thành viên của lớp này.')
    old = db.scalar(select(EnrollmentRequest).where(EnrollmentRequest.run_id == run.id, EnrollmentRequest.student_id == context.user.id, EnrollmentRequest.status == 'pending'))
    if old:
        response.status_code = 200
        return request_output(db, old)
    check_admission(db, run, course, 'approval', body.expected_revision)
    row = EnrollmentRequest(run_id=run.id, student_id=context.user.id, status='pending')
    db.add(row)
    db.commit()
    return request_output(db, row)


@router.get('/me/enrollment-requests')
def my_requests(status: Literal['all','pending','approved','rejected','cancelled'] = 'all', limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    query = select(EnrollmentRequest).where(EnrollmentRequest.student_id == context.user.id)
    if status != 'all':
        query = query.where(EnrollmentRequest.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(EnrollmentRequest.requested_at.desc(), EnrollmentRequest.id).limit(limit).offset(offset))
    return dict(items=[request_output(db,r) for r in rows], total=total, limit=limit, offset=offset)


@router.post('/me/enrollment-requests/{request_id}/cancel')
def cancel(request_id: UUID, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    row = db.get(EnrollmentRequest, request_id)
    if not row or row.student_id != context.user.id:
        raise ApiError(404, 'REQUEST_NOT_FOUND', 'Không tìm thấy yêu cầu.')
    locked_run(db, row.run_id)
    db.refresh(row)
    if row.status == 'cancelled':
        return request_output(db, row)
    if row.status != 'pending':
        raise ApiError(409, 'REQUEST_DECIDED', 'Yêu cầu đã được xử lý, không thể hủy.')
    row.status, row.decided_at, row.decided_by, row.reason = 'cancelled', utcnow(), context.user.id, 'Sinh viên hủy yêu cầu.'
    db.commit()
    return request_output(db, row)


@router.get('/teaching/runs/{run_id}/requests')
def run_requests(run_id: UUID, status: Literal['all','pending','approved','rejected','cancelled'] = 'pending', limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    owner_run(db, run_id, context.user.id)
    query = select(EnrollmentRequest).where(EnrollmentRequest.run_id == run_id)
    if status != 'all':
        query = query.where(EnrollmentRequest.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(EnrollmentRequest.requested_at, EnrollmentRequest.id).limit(limit).offset(offset))
    return dict(items=[request_output(db,r,True) for r in rows], total=total, limit=limit, offset=offset)


@router.post('/teaching/requests/{request_id}/decision')
def decide(request_id: UUID, body: DecisionInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    row = db.get(EnrollmentRequest, request_id)
    if not row:
        raise ApiError(404, 'REQUEST_NOT_FOUND', 'Không tìm thấy yêu cầu.')
    run, course = owner_run(db, row.run_id, context.user.id, lock=True)
    db.refresh(row)
    target = 'approved' if body.action == 'approve' else 'rejected'
    if row.status == target:
        return request_output(db, row, True)
    if row.status != 'pending':
        raise ApiError(409, 'REQUEST_DECIDED', 'Yêu cầu đã được xử lý; tải lại danh sách.')
    if body.action == 'approve':
        student = db.get(User, row.student_id, populate_existing=True)
        if not student.is_active or student.role != 'student':
            raise ApiError(409, 'STUDENT_UNAVAILABLE', 'Tài khoản sinh viên không còn hoạt động.')
        enrollment = existing_enrollment(db, run, row.student_id)
        if not enrollment:
            check_admission(db, run, course, 'approval')
            db.add(Enrollment(course_run_id=run.id, student_id=row.student_id, status='active'))
    row.status, row.decided_at, row.decided_by, row.reason = target, utcnow(), context.user.id, body.reason
    db.commit()
    return request_output(db, row, True)


@router.get('/me/run-status/{run_id}')
def run_status(run_id: UUID, context: AuthContext = Depends(require_student), db: Session = Depends(get_db)):
    run = db.get(CourseRun, run_id)
    if not run:
        raise ApiError(404, 'RUN_NOT_FOUND', 'Không tìm thấy lớp.')
    enrollment = db.scalar(select(Enrollment).where(Enrollment.course_run_id == run.id, Enrollment.student_id == context.user.id))
    request = db.scalar(select(EnrollmentRequest).where(EnrollmentRequest.run_id == run.id, EnrollmentRequest.student_id == context.user.id).order_by(EnrollmentRequest.requested_at.desc()).limit(1))
    publication = db.get(CoursePublication, run.course_id)
    visible = run.data_origin == 'real' and run.listed and run.status in ('active','closed') and publication and publication.status == 'published'
    if not (enrollment or request or visible):
        raise ApiError(404, 'RUN_NOT_FOUND', 'Không tìm thấy lớp.')
    return dict(run_id=run.id, course_id=run.course_id, enrollment_status=enrollment.status if enrollment else None, request=request_output(db,request) if request else None)


@router.get('/teaching/overview')
def teaching_overview(context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    courses = db.scalars(select(Course).where(Course.owner_teacher_id == context.user.id).order_by(Course.created_at.desc(), Course.id)).all()
    runs = db.scalars(select(CourseRun).where(CourseRun.course_id.in_([c.id for c in courses]), CourseRun.data_origin == 'real').order_by(CourseRun.created_at.desc(),CourseRun.id)).all()
    pending = db.scalar(select(func.count()).select_from(EnrollmentRequest).where(EnrollmentRequest.run_id.in_([r.id for r in runs]), EnrollmentRequest.status == 'pending')) or 0
    return dict(courses=[dict(id=c.id,code=c.code,title=c.title,publication_status=publication_for(db,c).status) for c in courses], runs=[dict(id=r.id,code=r.code,course_id=r.course_id,status=r.status,pending_requests=db.scalar(select(func.count()).select_from(EnrollmentRequest).where(EnrollmentRequest.run_id==r.id,EnrollmentRequest.status=='pending'))) for r in runs], pending_requests=pending)
