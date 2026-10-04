"""Explicit, idempotent foundation seed. Does not import PDFs or publish quizzes."""
import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import BACKEND_ROOT, REPO_ROOT, get_settings
from app.courses import ensure_dag
from app.db import get_engine
from app.errors import ApiError
from app.models import Course, CourseRun, Enrollment, Topic, TopicPrerequisite, User
from app.schemas import CourseInput, EmailInput, RegisterInput, RunInput, TopicInput
from app.security import hash_password


def seed_environment() -> dict:
    return {**dotenv_values(REPO_ROOT / ".env"), **dotenv_values(BACKEND_ROOT / ".env"), **os.environ}


def seed_user(db: Session, env: dict, prefix: str, role: str) -> User:
    email = env.get(f"{prefix}_EMAIL", "")
    if not email:
        raise ValueError(f"Cần cấu hình {prefix}_EMAIL")
    email = str(EmailInput(email=email).email)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        if user.role != role or not user.is_active:
            raise ValueError(f"Tài khoản {prefix}_EMAIL hiện có sai vai trò hoặc đang bị khóa")
        return user
    password = env.get(f"{prefix}_PASSWORD", "")
    if not password:
        raise ValueError(f"Cần cấu hình {prefix}_PASSWORD để tạo tài khoản")
    body = RegisterInput(email=email, password=password, display_name=env.get(f"{prefix}_DISPLAY_NAME") or ("Giảng viên StudyHub" if role == "teacher" else "Sinh viên StudyHub"))
    user = User(email=str(body.email), password_hash=hash_password(body.password), display_name=body.display_name, role=role)
    db.add(user)
    db.flush()
    return user


def seed() -> dict:
    get_settings()  # Mandatory configuration is checked before mutations.
    env = seed_environment()
    manifest_path = Path(env.get("COURSE_MANIFEST_PATH") or REPO_ROOT / "content/mobile_multiplatform/course_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    course_input = CourseInput(code=manifest["id"], title=manifest["title"])
    topic_inputs = {item["id"]: TopicInput(code=item["id"], title=item["title"], order_index=item["order"], objectives=item["objectives"]) for item in manifest["topics"]}
    if len(topic_inputs) != len(manifest["topics"]):
        raise ValueError("Manifest có mã chủ đề trùng")
    if len({item.order_index for item in topic_inputs.values()}) != len(topic_inputs):
        raise ValueError("Manifest có thứ tự chủ đề trùng")
    graph = {item["id"]: item["prerequisites"] for item in manifest["topics"]}
    if any(len(values) != len(set(values)) for values in graph.values()):
        raise ValueError("Manifest có tiên quyết trùng")
    if any(prerequisite not in topic_inputs for values in graph.values() for prerequisite in values):
        raise ValueError("Manifest có tiên quyết không tồn tại")
    ensure_dag(graph)
    with Session(get_engine(), expire_on_commit=False) as db, db.begin():
        teacher = seed_user(db, env, "BOOTSTRAP_TEACHER", "teacher")
        course = db.scalar(select(Course).where(Course.code == course_input.code).with_for_update())
        if course and course.owner_teacher_id != teacher.id:
            raise ValueError("Học phần hiện có thuộc giảng viên khác")
        if course is None:
            course = Course(**course_input.model_dump(), owner_teacher_id=teacher.id, content_revision=1)
            db.add(course)
            db.flush()
        topics = {topic.code: topic for topic in db.scalars(select(Topic).where(Topic.course_id == course.id))}
        new_codes = set()
        for code, body in topic_inputs.items():
            if code not in topics:
                topics[code] = Topic(course_id=course.id, **body.model_dump())
                db.add(topics[code])
                new_codes.add(code)
        db.flush()
        combined_graph = {topic.id: [] for topic in topics.values()}
        for edge in db.scalars(select(TopicPrerequisite).where(TopicPrerequisite.course_id == course.id)):
            combined_graph[edge.topic_id].append(edge.prerequisite_topic_id)
        for code in new_codes:
            combined_graph[topics[code].id] = [topics[prerequisite].id for prerequisite in graph[code]]
        ensure_dag(combined_graph)
        for code in new_codes:
            for prerequisite in graph[code]:
                db.add(TopicPrerequisite(course_id=course.id, topic_id=topics[code].id, prerequisite_topic_id=topics[prerequisite].id))
        if new_codes:
            course.content_revision += 1
        run_code = env.get("COURSE_RUN_CODE") or "MOBILE_2026"
        run = db.scalar(select(CourseRun).where(CourseRun.course_id == course.id, CourseRun.code == run_code))
        if run is None:
            start_date = date.fromisoformat(env["COURSE_RUN_START_DATE"]) if env.get("COURSE_RUN_START_DATE") else datetime.now(ZoneInfo("Asia/Bangkok")).date()
            body = RunInput(code=run_code, course_run_start_date=start_date, timezone="Asia/Bangkok")
            run = CourseRun(course_id=course.id, **body.model_dump(), status="active", data_origin="real")
            db.add(run)
            db.flush()
        student = None
        if env.get("DEMO_STUDENT_EMAIL"):
            student = seed_user(db, env, "DEMO_STUDENT", "student")
            existing = db.scalar(select(Enrollment).where(Enrollment.course_run_id == run.id, Enrollment.student_id == student.id))
            if existing is None:
                db.add(Enrollment(course_run_id=run.id, student_id=student.id, status="active"))
        result = {"course_code": course.code, "topic_count": len(topic_inputs), "run_code": run.code, "run_start_date": str(run.course_run_start_date), "student_enrolled": student is not None, "pdf_imported": False, "quiz_imported": False}
    return result


def main():
    try:
        print(json.dumps(seed(), ensure_ascii=False, indent=2))
    except ValidationError:
        raise SystemExit("Cấu hình seed không hợp lệ. Kiểm tra email, mật khẩu >=10 ký tự, tên và manifest.")
    except (OSError, json.JSONDecodeError, KeyError):
        raise SystemExit("Không đọc được manifest học phần hoặc cấu trúc manifest không hợp lệ.")
    except (ValueError, ApiError) as exc:
        raise SystemExit(exc.message if isinstance(exc, ApiError) else str(exc))
    except SQLAlchemyError:
        raise SystemExit("Seed thất bại do database hoặc xung đột dữ liệu. Chạy migration trước; dữ liệu chưa được commit.")


if __name__ == "__main__":
    main()
