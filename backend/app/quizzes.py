"""Immutable questions, explicit publication and server-side quiz grading."""
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.courses import Limit, Offset, accessible_run, owner_course
from app.db import get_db
from app.errors import ApiError
from app.learning_models import AttemptRequest, Question, QuestionVersion, QuizAttempt, QuizItem, QuizVersion
from app.learning_schemas import AnswersInput, BeginInput, QuestionContent, QuestionInput, QuizInput, SubmitInput
from app.models import Course, CourseRun, Enrollment, Topic
from app.resources import not_found, owner_topic, version_access
from app.security import AuthContext, get_auth, require_teacher, utcnow

router = APIRouter(tags=['quizzes'])


def check_sources(db, sources, course_id, published=False):
    for source in sources:
        version, _ = version_access(db, UUID(str(source['document_version_id'])), course_id, published=published)
        if not 1 <= source['pdf_page'] <= version.page_count:
            raise ApiError(422, 'QUESTION_SOURCE_INVALID', 'Trang nguồn của câu hỏi nằm ngoài PDF.')


def question_output(question, version):
    return {'id': version.id, 'question_id': question.id, 'code': question.code, 'version': version.version,
            'stem': version.stem, 'options': version.options, 'correct_option': version.correct_option,
            'explanation': version.explanation, 'sources': version.sources}


@router.post('/topics/{topic_id}/questions', status_code=201)
def create_question(topic_id: UUID, body: QuestionInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    topic, course = owner_topic(db, topic_id, context.user.id)
    payload = body.model_dump(mode='json', exclude={'code'})
    check_sources(db, payload['sources'], course.id)
    question = Question(topic_id=topic.id, code=body.code)
    db.add(question)
    db.flush()
    version = QuestionVersion(question_id=question.id, version=1, **payload)
    db.add(version)
    db.commit()
    return question_output(question, version)


@router.post('/questions/{question_id}/versions', status_code=201)
def create_question_version(question_id: UUID, body: QuestionContent, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    question = db.get(Question, question_id)
    if not question:
        not_found()
    _, course = owner_topic(db, question.topic_id, context.user.id)
    payload = body.model_dump(mode='json')
    check_sources(db, payload['sources'], course.id)
    number = (db.scalar(select(func.max(QuestionVersion.version)).where(QuestionVersion.question_id == question.id)) or 0) + 1
    version = QuestionVersion(question_id=question.id, version=number, **payload)
    db.add(version)
    db.commit()
    return question_output(question, version)


@router.get('/topics/{topic_id}/question-versions')
def question_versions(topic_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    owner_topic(db, topic_id, context.user.id)
    query = select(Question, QuestionVersion).join(QuestionVersion, QuestionVersion.question_id == Question.id).where(Question.topic_id == topic_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Question.code, QuestionVersion.version.desc()).limit(limit).offset(offset))
    return {'items': [question_output(q, v) for q, v in rows], 'total': total, 'limit': limit, 'offset': offset}


def quiz_items(db, quiz_id):
    return db.execute(select(QuizItem, QuestionVersion).join(QuestionVersion, QuestionVersion.id == QuizItem.question_version_id)
                      .where(QuizItem.quiz_version_id == quiz_id).order_by(QuizItem.order_index)).all()


def quiz_metadata(db, quiz):
    if quiz is None:
        return None
    count = db.scalar(select(func.count()).select_from(QuizItem).where(QuizItem.quiz_version_id == quiz.id))
    return {'id': quiz.id, 'published_version_id': quiz.id, 'version': quiz.version, 'status': quiz.status,
            'question_count': count, 'pass_percent': quiz.pass_percent, 'min_questions': quiz.min_questions}


def current_quiz(db, topic_id):
    return db.scalar(select(QuizVersion).where(QuizVersion.topic_id == topic_id, QuizVersion.status == 'published'))


@router.post('/topics/{topic_id}/quiz-versions', status_code=201)
def create_quiz(topic_id: UUID, body: QuizInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    topic, _ = owner_topic(db, topic_id, context.user.id)
    ids = set(db.scalars(select(QuestionVersion.id).join(Question, Question.id == QuestionVersion.question_id)
                         .where(Question.topic_id == topic.id, QuestionVersion.id.in_(body.question_version_ids))))
    if ids != set(body.question_version_ids):
        raise ApiError(422, 'QUIZ_QUESTION_INVALID', 'Câu hỏi phải thuộc chủ đề đang biên soạn.')
    # A quiz cannot contain two revisions of the same logical question.
    logical = db.scalars(select(QuestionVersion.question_id).where(QuestionVersion.id.in_(ids))).all()
    if len(set(logical)) != len(logical):
        raise ApiError(422, 'QUIZ_QUESTION_INVALID', 'Chỉ chọn một phiên bản của mỗi câu hỏi.')
    number = (db.scalar(select(func.max(QuizVersion.version)).where(QuizVersion.topic_id == topic.id)) or 0) + 1
    quiz = QuizVersion(topic_id=topic.id, version=number, status='draft', pass_percent=70, min_questions=3)
    db.add(quiz)
    db.flush()
    db.add_all([QuizItem(quiz_version_id=quiz.id, question_version_id=value, order_index=index)
                for index, value in enumerate(body.question_version_ids, 1)])
    db.commit()
    return quiz_metadata(db, quiz)


@router.get('/topics/{topic_id}/quiz-versions')
def list_quizzes(topic_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    owner_topic(db, topic_id, context.user.id)
    query = select(QuizVersion).where(QuizVersion.topic_id == topic_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items': [quiz_metadata(db, q) for q in db.scalars(query.order_by(QuizVersion.version.desc()).limit(limit).offset(offset))], 'total': total, 'limit': limit, 'offset': offset}


@router.get('/quiz-versions/{version_id}')
def read_quiz(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    quiz = db.get(QuizVersion, version_id)
    if not quiz:
        not_found()
    owner_topic(db, quiz.topic_id, context.user.id)
    result = quiz_metadata(db, quiz)
    result['items'] = [{'quiz_version_item_id': item.id, **question_output(db.get(Question, version.question_id), version)} for item, version in quiz_items(db, quiz.id)]
    return result


@router.post('/quiz-versions/{version_id}/publish')
def publish_quiz(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    quiz = db.get(QuizVersion, version_id)
    if not quiz:
        not_found()
    _, course = owner_topic(db, quiz.topic_id, context.user.id)
    db.refresh(quiz)
    if quiz.status == 'published':
        return quiz_metadata(db, quiz)
    if quiz.status != 'draft':
        raise ApiError(409, 'QUIZ_IMMUTABLE', 'Quiz đã nghỉ không thể công bố lại. Hãy tạo bản mới.')
    items = quiz_items(db, quiz.id)
    if len(items) < quiz.min_questions:
        raise ApiError(422, 'QUIZ_TOO_SHORT', 'Quiz cần ít nhất 3 câu hỏi.')
    for _, version in items:
        check_sources(db, version.sources, course.id, published=True)
    old = current_quiz(db, quiz.topic_id)
    if old:
        old.status = 'retired'
        db.flush()
    quiz.status, quiz.published_at = 'published', utcnow()
    course.content_revision += 1
    db.commit()
    return quiz_metadata(db, quiz)


@router.get('/course-runs/{run_id}/topics/{topic_id}/quiz')
def student_quiz(run_id: UUID, topic_id: UUID, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run = accessible_run(db, run_id, context)
    topic = db.get(Topic, topic_id)
    if not topic or topic.course_id != run.course_id:
        not_found()
    return {'quiz': quiz_metadata(db, current_quiz(db, topic.id))}


def student_enrollment(db, run_id, context, writing=False):
    if context.user.role != 'student':
        raise ApiError(403, 'ROLE_FORBIDDEN', 'Chức năng này dành cho sinh viên.')
    run = accessible_run(db, run_id, context)
    if writing:
        # All student mutations use the same course -> run -> enrollment lock order
        # as publication, run edits and enrollment revocation.
        db.scalar(select(Course).where(Course.id == run.course_id).with_for_update())
        run = db.scalar(select(CourseRun).where(CourseRun.id == run_id).with_for_update().execution_options(populate_existing=True))
    query = select(Enrollment).where(Enrollment.course_run_id == run_id, Enrollment.student_id == context.user.id, Enrollment.status == 'active')
    if writing:
        query = query.with_for_update().execution_options(populate_existing=True)
    enrollment = db.scalar(query)
    if enrollment is None:
        not_found()
    if writing and (run.status != 'active' or run.data_origin != 'real'):
        raise ApiError(409, 'RUN_READ_ONLY', 'Chỉ ghi bài làm và log trong lượt học thật đang mở.')
    return run, enrollment


def own_attempt(db, attempt_id, context, writing=False):
    attempt = db.get(QuizAttempt, attempt_id)
    enrollment = db.get(Enrollment, attempt.enrollment_id) if attempt else None
    if not enrollment or enrollment.student_id != context.user.id:
        not_found()
    run, enrollment = student_enrollment(db, enrollment.course_run_id, context, writing)
    if writing:
        attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update().execution_options(populate_existing=True))
    return attempt, run, enrollment


def attempt_output(db, attempt):
    quiz = db.get(QuizVersion, attempt.quiz_version_id)
    current = current_quiz(db, quiz.topic_id)
    complete = attempt.status == 'completed'
    result = {'id': attempt.id, 'quiz_version_id': quiz.id, 'topic_id': quiz.topic_id, 'status': attempt.status,
              'answer_revision': attempt.answer_revision, 'started_at': attempt.started_at, 'completed_at': attempt.completed_at,
              'graded_at': attempt.graded_at, 'path_revision': attempt.path_revision, 'pass_percent': quiz.pass_percent, 'items': []}
    for item, question in quiz_items(db, quiz.id):
        chosen = attempt.answers.get(str(item.id))
        row = {'quiz_version_item_id': item.id, 'stem': question.stem, 'options': question.options, 'selected_option': chosen}
        if complete:
            row.update(correct_option=question.correct_option, is_correct=chosen == question.correct_option,
                       explanation=question.explanation, sources=question.sources)
        result['items'].append(row)
    if complete:
        result.update(correct_count=attempt.correct_count, total_questions=attempt.total_questions,
                      score_percent=100 * attempt.correct_count / attempt.total_questions,
                      passed_for_attempt_version=100 * attempt.correct_count >= quiz.pass_percent * attempt.total_questions and attempt.total_questions >= quiz.min_questions,
                      counts_for_current_mastery=current is not None and current.id == quiz.id)
    return result


@router.post('/course-runs/{run_id}/topics/{topic_id}/attempts', status_code=201)
def begin_attempt(run_id: UUID, topic_id: UUID, body: BeginInput, response: Response, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run, enrollment = student_enrollment(db, run_id, context, writing=True)
    topic = db.get(Topic, topic_id)
    if not topic or topic.course_id != run.course_id:
        not_found()
    existing = db.get(AttemptRequest, (enrollment.id, body.request_key))
    if existing:
        attempt = db.get(QuizAttempt, existing.attempt_id)
        quiz = db.get(QuizVersion, attempt.quiz_version_id)
        if quiz.topic_id != topic.id or quiz.id != body.published_quiz_version_id:
            raise ApiError(409, 'ATTEMPT_KEY_CONFLICT', 'Mã yêu cầu đã dùng cho bài làm khác.')
        response.status_code = 200
        return attempt_output(db, attempt)
    quiz = current_quiz(db, topic.id)
    if not quiz or quiz.id != body.published_quiz_version_id:
        raise ApiError(409, 'QUIZ_VERSION_CHANGED', 'Quiz đã thay đổi hoặc chưa được công bố.', {'published_quiz_version_id': str(quiz.id) if quiz else None})
    attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.enrollment_id == enrollment.id, QuizAttempt.quiz_version_id == quiz.id, QuizAttempt.status == 'in_progress'))
    if attempt:
        response.status_code = 200
    else:
        attempt = QuizAttempt(enrollment_id=enrollment.id, quiz_version_id=quiz.id, status='in_progress', answer_revision=0, answers={})
        db.add(attempt)
        db.flush()
    db.add(AttemptRequest(enrollment_id=enrollment.id, request_key=body.request_key, attempt_id=attempt.id))
    db.commit()
    return attempt_output(db, attempt)


@router.get('/attempts/{attempt_id}')
def read_attempt(attempt_id: UUID, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    attempt, _, _ = own_attempt(db, attempt_id, context)
    return attempt_output(db, attempt)


def check_revision(attempt, expected):
    if expected != attempt.answer_revision:
        raise ApiError(409, 'ANSWER_REVISION_CONFLICT', 'Bài làm đã được cập nhật ở phiên khác. Tải lại bài làm.', {'current_revision': attempt.answer_revision})


@router.put('/attempts/{attempt_id}/answers')
def save_answers(attempt_id: UUID, body: AnswersInput, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    attempt, _, _ = own_attempt(db, attempt_id, context, writing=True)
    if attempt.status != 'in_progress':
        raise ApiError(409, 'ATTEMPT_COMPLETED', 'Bài đã nộp không thể sửa.')
    check_revision(attempt, body.expected_revision)
    ids = {item.id for item, _ in quiz_items(db, attempt.quiz_version_id)}
    selected = [answer.quiz_version_item_id for answer in body.answers]
    if len(selected) != len(set(selected)) or not set(selected).issubset(ids):
        raise ApiError(422, 'ANSWER_ITEM_INVALID', 'Câu trả lời trùng hoặc không thuộc bài làm.')
    attempt.answers = {str(answer.quiz_version_item_id): answer.selected_option for answer in body.answers}
    attempt.answer_revision += 1
    db.commit()
    return attempt_output(db, attempt)


@router.post('/attempts/{attempt_id}/submit')
def submit_attempt(attempt_id: UUID, body: SubmitInput, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    from app.paths import ensure_path
    attempt, run, enrollment = own_attempt(db, attempt_id, context, writing=True)
    if attempt.status == 'completed':
        return attempt_output(db, attempt)
    check_revision(attempt, body.expected_revision)
    items = quiz_items(db, attempt.quiz_version_id)
    attempt.correct_count = sum(attempt.answers.get(str(item.id)) == version.correct_option for item, version in items)
    attempt.total_questions = len(items)
    attempt.status = 'completed'
    attempt.completed_at = attempt.graded_at = utcnow()
    db.flush()
    attempt.path_revision = ensure_path(db, run, enrollment)['revision']
    db.commit()
    return attempt_output(db, attempt)


@router.get('/course-runs/{run_id}/results')
def results(run_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _, enrollment = student_enrollment(db, run_id, context)
    query = select(QuizAttempt).where(QuizAttempt.enrollment_id == enrollment.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    attempts = db.scalars(query.order_by(QuizAttempt.started_at.desc(), QuizAttempt.id).limit(limit).offset(offset))
    return {'items': [attempt_output(db, a) for a in attempts], 'total': total, 'limit': limit, 'offset': offset}
