"""Administrative CLI for a separate synthetic timeline; never backdates a real run."""
import argparse
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.features import cutoff_bounds
from app.learning_models import Document, DocumentVersion, LearningEvent
from app.models import Course, CourseRun, Enrollment, User


def seed_demo(course_code, student_email):
    with Session(get_engine()) as db:
        course = db.scalar(select(Course).where(Course.code == course_code).with_for_update())
        student = db.scalar(select(User).where(User.email == student_email.strip().lower(), User.role == 'student', User.is_active.is_(True)))
        if not course or not student:
            raise ValueError('Course/student not found; seed the foundation first.')
        version = db.scalar(select(DocumentVersion).join(Document).where(Document.course_id == course.id,
            Document.status == 'published', DocumentVersion.status == 'ready').order_by(Document.code, DocumentVersion.version).limit(1))
        if not version:
            raise ValueError('Publish at least one PDF in this course before creating the demo.')
        run = db.scalar(select(CourseRun).where(CourseRun.course_id == course.id, CourseRun.code == 'ML_DEMO_42').with_for_update())
        if run and run.data_origin != 'synthetic':
            raise ValueError('ML_DEMO_42 is already used by a real run; refusing to modify it.')
        if not run:
            run = CourseRun(course_id=course.id, code='ML_DEMO_42', data_origin='synthetic', status='closed',
                timezone='Asia/Bangkok', course_run_start_date=datetime.now(ZoneInfo('Asia/Bangkok')).date() - timedelta(days=60))
            db.add(run)
            db.flush()
        lower, upper = cutoff_bounds(run.course_run_start_date, run.timezone)
        if datetime.now(ZoneInfo('UTC')) < upper:
            raise ValueError('Existing synthetic timeline has not reached cutoff; refusing to rewrite it.')
        enrollment = db.scalar(select(Enrollment).where(Enrollment.course_run_id == run.id, Enrollment.student_id == student.id).with_for_update())
        if not enrollment:
            enrollment = Enrollment(course_run_id=run.id, student_id=student.id, status='active')
            db.add(enrollment)
            db.flush()
        if enrollment.status != 'active':
            raise ValueError('Demo enrollment is inactive; review enrollment before reseeding.')
        for day in [0, 2, 42]:
            event_id = uuid5(NAMESPACE_URL, f'studyhub:synthetic:{enrollment.id}:page:{day}')
            if not db.scalar(select(LearningEvent.id).where(LearningEvent.enrollment_id == enrollment.id, LearningEvent.client_event_id == event_id)):
                at = lower + timedelta(days=day, hours=12)
                db.add(LearningEvent(enrollment_id=enrollment.id, client_event_id=event_id,
                    viewer_session_id=uuid5(NAMESPACE_URL, f'studyhub:synthetic:{enrollment.id}:viewer'),
                    type='page_view', document_version_id=version.id, pdf_page=1,
                    occurred_at=at, received_at=at, data_origin='synthetic'))
        db.commit()
        print('Synthetic run ML_DEMO_42 ready. Real-run dates, attempts and events are preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course-code', required=True)
    parser.add_argument('--student-email', required=True)
    args = parser.parse_args()
    try:
        seed_demo(args.course_code, args.student_email)
    except ValueError as error:
        parser.exit(1, f'{error}\n')
