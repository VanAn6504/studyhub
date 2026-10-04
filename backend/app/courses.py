from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models import Course, CourseRun, Enrollment, Topic, TopicPrerequisite, User
from app.schemas import (
    CourseInput, CourseOutput, EnrollmentInput, EnrollmentOutput, EnrollmentPatch, Page,
    PrerequisitesInput, RunInput, RunOutput, RunPatch, TopicInput, TopicOutput,
)
from app.security import AuthContext, get_auth, require_teacher

router = APIRouter(tags=["courses"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def owner_course(db: Session, course_id: UUID, teacher_id: UUID, lock: bool = False) -> Course:
    query = select(Course).where(Course.id == course_id, Course.owner_teacher_id == teacher_id)
    if lock:
        query = query.with_for_update()
    course = db.scalar(query)
    if course is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy học phần.")
    return course


def owner_run(db: Session, run_id: UUID, teacher_id: UUID, lock: bool = False) -> tuple[CourseRun, Course]:
    run = db.get(CourseRun, run_id)
    if run is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy lượt học.")
    course = owner_course(db, run.course_id, teacher_id, lock=lock)
    if lock:
        run = db.scalar(select(CourseRun).where(CourseRun.id == run_id).with_for_update().execution_options(populate_existing=True))
    return run, course


def accessible_run(db: Session, run_id: UUID, context: AuthContext) -> CourseRun:
    if context.user.role == "teacher":
        return owner_run(db, run_id, context.user.id)[0]
    run = db.scalar(
        select(CourseRun).join(Enrollment, Enrollment.course_run_id == CourseRun.id)
        .where(CourseRun.id == run_id, Enrollment.student_id == context.user.id, Enrollment.status == "active")
    )
    if run is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy lượt học.")
    return run


def run_output(db: Session, run: CourseRun, course: Course) -> RunOutput:
    count = db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.course_run_id == run.id, Enrollment.status == "active")) or 0
    return RunOutput(id=run.id, code=run.code, course_id=course.id, course_title=course.title, course_run_start_date=run.course_run_start_date, timezone=run.timezone, status=run.status, data_origin=run.data_origin, student_count=count)


def topic_outputs(db: Session, topics: list[Topic]) -> list[TopicOutput]:
    prerequisites: dict[UUID, list[UUID]] = {topic.id: [] for topic in topics}
    if topics:
        edges = db.execute(
            select(TopicPrerequisite.topic_id, TopicPrerequisite.prerequisite_topic_id)
            .join(Topic, Topic.id == TopicPrerequisite.prerequisite_topic_id)
            .where(TopicPrerequisite.topic_id.in_(prerequisites))
            .order_by(Topic.order_index, Topic.id)
        ).all()
        for topic_id, prerequisite_id in edges:
            prerequisites[topic_id].append(prerequisite_id)
    return [TopicOutput(id=topic.id, code=topic.code, title=topic.title, order_index=topic.order_index, objectives=topic.objectives, prerequisite_topic_ids=prerequisites[topic.id]) for topic in topics]


def ensure_dag(graph: dict[UUID, list[UUID]]):
    pending = {node: len(prerequisites) for node, prerequisites in graph.items()}
    dependents = {node: [] for node in graph}
    for node, prerequisites in graph.items():
        for prerequisite in prerequisites:
            if prerequisite not in graph:
                raise ApiError(422, "PREREQUISITE_INVALID", "Chủ đề tiên quyết không tồn tại trong học phần.")
            dependents[prerequisite].append(node)
    ready = [node for node, degree in pending.items() if degree == 0]
    visited = 0
    while ready:
        node = ready.pop()
        visited += 1
        for dependent in dependents[node]:
            pending[dependent] -= 1
            if pending[dependent] == 0:
                ready.append(dependent)
    if visited != len(graph):
        raise ApiError(422, "PREREQUISITE_CYCLE", "Quan hệ tiên quyết tạo chu trình.")


@router.get("/courses", response_model=Page[CourseOutput])
def list_courses(limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    query = select(Course).where(Course.owner_teacher_id == context.user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Course.created_at, Course.id).limit(limit).offset(offset)).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/courses", response_model=CourseOutput, status_code=201)
def create_course(body: CourseInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    course = Course(code=body.code, title=body.title, owner_teacher_id=context.user.id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/course-runs", response_model=Page[RunOutput])
def list_runs(limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    query = select(CourseRun, Course).join(Course, Course.id == CourseRun.course_id)
    if context.user.role == "teacher":
        query = query.where(Course.owner_teacher_id == context.user.id)
    else:
        query = query.join(Enrollment, Enrollment.course_run_id == CourseRun.id).where(Enrollment.student_id == context.user.id, Enrollment.status == "active")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(CourseRun.created_at, CourseRun.id).limit(limit).offset(offset)).all()
    return {"items": [run_output(db, run, course) for run, course in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/courses/{course_id}/runs", response_model=RunOutput, status_code=201)
def create_run(course_id: UUID, body: RunInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    course = owner_course(db, course_id, context.user.id, lock=True)
    run = CourseRun(course_id=course.id, **body.model_dump(), status="draft", data_origin="real")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run_output(db, run, course)


@router.patch("/course-runs/{run_id}", response_model=RunOutput)
def patch_run(run_id: UUID, body: RunPatch, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    run, course = owner_run(db, run_id, context.user.id, lock=True)
    if run.data_origin != "real":
        raise ApiError(409, "RUN_READ_ONLY", "Không chỉnh lượt học mô phỏng qua API.")
    # This migration has no event or attempt tables. Their module must guard date/timezone
    # changes under this same run lock once learning activity is introduced.
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(run, field, value)
    db.commit()
    return run_output(db, run, course)


@router.post("/course-runs/{run_id}/enrollments", response_model=EnrollmentOutput, status_code=201)
def create_enrollment(run_id: UUID, body: EnrollmentInput, response: Response, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    run, _ = owner_run(db, run_id, context.user.id, lock=True)
    if run.data_origin != "real":
        raise ApiError(409, "RUN_READ_ONLY", "Không chỉnh lượt học mô phỏng qua API.")
    student = db.scalar(select(User).where(User.email == str(body.student_email), User.role == "student", User.is_active.is_(True)))
    if student is None:
        raise ApiError(404, "STUDENT_NOT_FOUND", "Không tìm thấy tài khoản sinh viên đang hoạt động.")
    existing = db.scalar(select(Enrollment).where(Enrollment.course_run_id == run.id, Enrollment.student_id == student.id))
    if existing:
        if existing.status == "inactive":
            raise ApiError(409, "ENROLLMENT_INACTIVE", "Cần kích hoạt lại lượt đăng ký học hiện có.")
        response.status_code = 200
        return existing
    enrollment = Enrollment(course_run_id=run.id, student_id=student.id, status="active")
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.patch("/enrollments/{enrollment_id}", response_model=EnrollmentOutput)
def patch_enrollment(enrollment_id: UUID, body: EnrollmentPatch, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy đăng ký học.")
    run, _ = owner_run(db, enrollment.course_run_id, context.user.id, lock=True)
    if run.data_origin != "real":
        raise ApiError(409, "RUN_READ_ONLY", "Không chỉnh lượt học mô phỏng qua API.")
    enrollment = db.scalar(select(Enrollment).where(Enrollment.id == enrollment_id).with_for_update().execution_options(populate_existing=True))
    enrollment.status = body.status
    db.commit()
    return enrollment


@router.get("/courses/{course_id}/topics", response_model=Page[TopicOutput])
def list_course_topics(course_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    owner_course(db, course_id, context.user.id)
    return topics_page(db, course_id, limit, offset)


def topics_page(db: Session, course_id: UUID, limit: int, offset: int):
    query = select(Topic).where(Topic.course_id == course_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    topics = db.scalars(query.order_by(Topic.order_index, Topic.id).limit(limit).offset(offset)).all()
    return {"items": topic_outputs(db, topics), "total": total, "limit": limit, "offset": offset}


@router.get("/course-runs/{run_id}/topics", response_model=Page[TopicOutput])
def list_run_topics(run_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run = accessible_run(db, run_id, context)
    return topics_page(db, run.course_id, limit, offset)


@router.post("/courses/{course_id}/topics", response_model=TopicOutput, status_code=201)
def create_topic(course_id: UUID, body: TopicInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    course = owner_course(db, course_id, context.user.id, lock=True)
    topic = Topic(course_id=course.id, **body.model_dump())
    db.add(topic)
    course.content_revision += 1
    db.commit()
    db.refresh(topic)
    return topic_outputs(db, [topic])[0]


@router.put("/topics/{topic_id}/prerequisites", response_model=TopicOutput)
def replace_prerequisites(topic_id: UUID, body: PrerequisitesInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy chủ đề.")
    course = owner_course(db, topic.course_id, context.user.id, lock=True)
    topic_ids = set(db.scalars(select(Topic.id).where(Topic.course_id == course.id)).all())
    requested = body.prerequisite_topic_ids
    if topic.id in requested or any(item not in topic_ids for item in requested):
        raise ApiError(422, "PREREQUISITE_INVALID", "Tiên quyết phải là chủ đề khác trong cùng học phần.")
    graph = {item: [] for item in topic_ids}
    for edge in db.scalars(select(TopicPrerequisite).where(TopicPrerequisite.course_id == course.id)):
        graph[edge.topic_id].append(edge.prerequisite_topic_id)
    old = set(graph[topic.id])
    graph[topic.id] = requested
    ensure_dag(graph)
    if old != set(requested):
        db.execute(delete(TopicPrerequisite).where(TopicPrerequisite.topic_id == topic.id))
        db.add_all([TopicPrerequisite(topic_id=topic.id, prerequisite_topic_id=item, course_id=course.id) for item in requested])
        course.content_revision += 1
        db.commit()
    return topic_outputs(db, [topic])[0]
