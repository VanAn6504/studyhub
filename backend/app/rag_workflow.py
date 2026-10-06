"""Explicit PDF opt-in, background preparation and page-level review."""
import hashlib
from collections import defaultdict
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.courses import Limit, Offset, owner_course
from app.db import get_db, get_engine
from app.errors import ApiError
from app.models import User
from app.rag import corpus_query, extract_corpus, index_corpus, owned_version
from app.rag_models import DocumentChunk, RagPreparation
from app.rag_policy import automatic_candidate, eligible, issues
from app.rag_schemas import PageReviewInput
from app.security import AuthContext, require_teacher, utcnow

router = APIRouter(tags=['rag'])
LEASE = timedelta(minutes=10)


def page_revision(chunks):
    return hashlib.sha256('|'.join(f'{c.id}:{c.revision}' for c in sorted(chunks, key=lambda c: c.chunk_index)).encode()).hexdigest()


def pages(db, version_id):
    groups = defaultdict(list)
    for chunk in db.scalars(corpus_query(version_id).order_by(DocumentChunk.pdf_page, DocumentChunk.chunk_index)):
        groups[chunk.pdf_page].append(chunk)
    result = []
    for number, chunks in groups.items():
        usable = [c for c in chunks if eligible(c)]
        unresolved = [c for c in chunks if c.review_status == 'pending' and not c.auto_eligible]
        state = 'needs_review' if unresolved else 'checked' if any(c.review_status == 'reviewed' for c in usable) else 'automatic' if usable else 'excluded'
        result.append({'pdf_page': number, 'revision': page_revision(chunks), 'state': state,
            'issues': sorted({flag for c in unresolved for flag in issues(c)}),
            'usable_segments': len(usable), 'text': '\n\n'.join(c.text for c in chunks),
            'text_only': any(c.extraction_method == 'pypdf' and 'contains_images' in c.flags for c in usable),
            'has_transcription': any(c.extraction_method == 'manual' for c in chunks)})
    return result


def state_output(db, version, document):
    preparation = db.get(RagPreparation, version.id)
    page_list = pages(db, version.id)
    legacy = preparation is None and any(p['usable_segments'] for p in page_list)
    status = preparation.status if preparation else 'unprepared'
    error = preparation.error_code if preparation else None
    enabled = preparation.enabled if preparation else legacy
    if preparation and status == 'processing' and preparation.started_at < utcnow() - LEASE:
        status, error = 'failed', 'RAG_PROCESS_INTERRUPTED'
    if not enabled and preparation:
        status = 'disabled'
    return {'document_version_id': version.id, 'enabled': enabled, 'legacy': legacy,
        'status': status, 'error_code': error, 'document_status': document.status,
        'counts': {name: sum(p['state'] == name for p in page_list) for name in ('automatic', 'checked', 'needs_review', 'excluded')},
        'usable_pages': sum(p['usable_segments'] > 0 for p in page_list), 'total_pages': version.page_count}


@router.get('/document-versions/{version_id}/rag')
def rag_state(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, document = owned_version(db, version_id, context)
    return state_output(db, version, document)


def processing(state):
    return state.status == 'processing' and state.started_at > utcnow() - LEASE


def begin(state):
    state.status, state.error_code = 'processing', None
    state.generation_id, state.started_at = uuid4(), utcnow()


def prepare(version_id, generation_id, teacher_id):
    """Saved generation prevents a disabled/retried job from restoring source access."""
    context = SimpleNamespace(user=SimpleNamespace(id=teacher_id))
    try:
        with Session(get_engine(), expire_on_commit=False) as db:
            version, _ = owned_version(db, version_id, context, lock=True)
            state = db.get(RagPreparation, version_id)
            teacher = db.get(User, teacher_id)
            if not state or not state.enabled or state.generation_id != generation_id:
                return
            if not teacher or teacher.role != 'teacher' or not teacher.is_active:
                raise ApiError(403, 'RAG_OWNER_UNAVAILABLE', 'Giảng viên không còn quyền xử lý nguồn.')
            extract_corpus(version_id, context, db)
            owned_version(db, version_id, context, lock=True)
            state = db.get(RagPreparation, version_id, populate_existing=True)
            if not state.enabled or state.generation_id != generation_id:
                return
            for chunk in db.scalars(corpus_query(version.id)):
                if chunk.review_status == 'pending':
                    candidate = automatic_candidate(chunk)
                    if chunk.auto_eligible != candidate:
                        chunk.auto_eligible = candidate
                        chunk.revision += 1
            db.commit()
            index_corpus(version_id, context, db)
            owned_version(db, version_id, context, lock=True)
            state = db.get(RagPreparation, version_id, populate_existing=True)
            if state.enabled and state.generation_id == generation_id:
                state.status = 'needs_review' if any(p['state'] == 'needs_review' for p in pages(db, version_id)) else 'ready'
                db.commit()
    except Exception as error:
        # Never persist exception text: it may include connection/provider details.
        with Session(get_engine()) as db:
            state = db.scalar(select(RagPreparation).where(RagPreparation.document_version_id == version_id).with_for_update())
            if state and state.enabled and state.generation_id == generation_id:
                state.status = 'failed'
                state.error_code = error.code if isinstance(error, ApiError) else 'RAG_PREPARATION_FAILED'
                db.commit()


@router.post('/document-versions/{version_id}/rag/enable', status_code=202)
def enable_rag(version_id: UUID, tasks: BackgroundTasks, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, document = owned_version(db, version_id, context, lock=True)
    state = db.get(RagPreparation, version.id)
    if state and state.enabled and processing(state):
        return state_output(db, version, document)
    if state and state.enabled and state.status in ('ready', 'needs_review') and document.status == 'published':
        return state_output(db, version, document)
    if state is None:
        state = RagPreparation(document_version_id=version.id)
        db.add(state)
    state.enabled, state.authorized_by, state.authorized_at = True, context.user.id, utcnow()
    if document.status != 'published':
        course = owner_course(db, document.course_id, context.user.id)
        document.status = 'published'
        course.content_revision += 1
    begin(state)
    db.commit()
    tasks.add_task(prepare, version.id, state.generation_id, context.user.id)
    return state_output(db, version, document)


@router.post('/document-versions/{version_id}/rag/disable')
def disable_rag(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, document = owned_version(db, version_id, context, lock=True)
    state = db.get(RagPreparation, version.id)
    if state is None:
        state = RagPreparation(document_version_id=version.id, status='unprepared')
        db.add(state)
    state.enabled, state.generation_id = False, uuid4()
    db.commit()
    return state_output(db, version, document)


@router.get('/document-versions/{version_id}/rag/pages')
def list_pages(version_id: UUID, needs_review_only: bool = False, limit: Limit = 20, offset: Offset = 0,
               context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    owned_version(db, version_id, context)
    items = pages(db, version_id)
    if needs_review_only:
        items = [p for p in items if p['state'] == 'needs_review']
    return {'items': items[offset:offset + limit], 'total': len(items), 'limit': limit, 'offset': offset}


@router.patch('/document-versions/{version_id}/rag/pages/{pdf_page}')
def review_page(version_id: UUID, pdf_page: int, body: PageReviewInput, tasks: BackgroundTasks,
                context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, document = owned_version(db, version_id, context, lock=True)
    if not 1 <= pdf_page <= version.page_count:
        raise ApiError(422, 'PDF_PAGE_INVALID', 'Trang nguồn nằm ngoài PDF.')
    state = db.get(RagPreparation, version.id)
    if not state or not state.enabled:
        raise ApiError(409, 'RAG_NOT_ENABLED', 'Bấm công bố và dùng cho trợ giảng trước khi lưu quyết định theo trang.')
    if state and processing(state) and state.enabled:
        raise ApiError(409, 'RAG_PROCESSING', 'Nguồn đang xử lý. Hãy đợi hoàn tất rồi kiểm tra trang.')
    chunks = list(db.scalars(corpus_query(version_id).where(DocumentChunk.pdf_page == pdf_page)))
    if not chunks:
        raise ApiError(409, 'CORPUS_NOT_EXTRACTED', 'Bật trợ giảng cho tài liệu để chuẩn bị nguồn trước.')
    if page_revision(chunks) != body.revision:
        raise ApiError(409, 'PAGE_REVISION_CONFLICT', 'Trang đã thay đổi ở tab khác. Hãy tải lại nguồn.')
    if body.transcription:
        # Add a new immutable source and exclude previous extraction on this page.
        index = max(c.chunk_index for c in chunks) + 1
        new = DocumentChunk(document_version_id=version.id, pdf_page=pdf_page, chunk_index=index,
            text=body.transcription, source_hash=hashlib.sha256(f'{version.sha256}:{pdf_page}:{index}:{body.transcription}'.encode()).hexdigest(),
            extraction_method='manual', flags=['manual_transcription'], kind='content', review_status='pending', revision=1)
        db.add(new)
        chunks.append(new)
    allowed = [c for c in chunks if len(c.text.strip()) >= 20 and (not body.transcription or c is new)]
    if body.action == 'allow' and not allowed:
        raise ApiError(422, 'PAGE_EMPTY', 'Trang thiếu chữ; nhập bản phiên chép đã đối chiếu PDF trước khi cho phép.')
    for chunk in chunks:
        accept = body.action == 'allow' and chunk in allowed
        chunk.review_status, chunk.auto_eligible = ('reviewed' if accept else 'rejected'), False
        if accept:
            chunk.kind = 'content'
        chunk.reviewed_by, chunk.reviewed_at = context.user.id, utcnow()
        chunk.revision += 1
    if state and state.enabled:
        begin(state)
    db.commit()
    if state and state.enabled:
        tasks.add_task(prepare, version.id, state.generation_id, context.user.id)
    return state_output(db, version, document)
