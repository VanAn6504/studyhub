"""Explicit PDF opt-in, background preparation and page-level review."""
import hashlib
from collections import defaultdict
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.courses import Limit, Offset, owner_course
from app.db import get_db, get_engine
from app.errors import ApiError
from app.models import Topic, User
from app.rag import corpus_query, extract_corpus, index_corpus, owned_version
from app.rag_models import DocumentChunk, RagPreparation, RagPageCheckpoint
from app.rag_policy import automatic_candidate, eligible, eligible_clause, issues
from app.rag_schemas import PageReviewInput, RagScopeInput
from app.rag_scope import selected_pages
from app.security import AuthContext, require_teacher, utcnow

router = APIRouter(tags=['rag'])
LEASE = timedelta(minutes=10)


def page_revision(chunks):
    return hashlib.sha256('|'.join(f'{c.id}:{c.revision}' for c in sorted(chunks, key=lambda c: c.chunk_index)).encode()).hexdigest()


def pages(db, version_id, numbers=None):
    groups = defaultdict(list)
    query=corpus_query(version_id)
    if numbers is not None:query=query.where(DocumentChunk.pdf_page.in_(numbers))
    for chunk in db.scalars(query.order_by(DocumentChunk.pdf_page, DocumentChunk.chunk_index)):
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
    wanted=selected_pages(preparation.scope_ranges if preparation else [],version.page_count)
    summaries=db.execute(select(DocumentChunk.pdf_page,
        func.count().filter(eligible_clause()),
        func.bool_or(and_(DocumentChunk.review_status=='pending',DocumentChunk.auto_eligible.is_(False))),
        func.bool_or(and_(eligible_clause(),DocumentChunk.review_status=='reviewed')),
        func.count().filter(and_(eligible_clause(),DocumentChunk.embedding.is_not(None),
            DocumentChunk.embedding_code==preparation.embedding_code if preparation and preparation.embedding_code else True)))
        .where(DocumentChunk.document_version_id==version.id,DocumentChunk.pdf_page.in_(wanted)).group_by(DocumentChunk.pdf_page)).all()
    page_list=[dict(usable_segments=usable,state='needs_review' if unresolved else 'checked' if checked else 'automatic' if usable else 'excluded',indexed=indexed) for _,usable,unresolved,checked,indexed in summaries]
    legacy = preparation is None and any(p['usable_segments'] for p in page_list)
    status = preparation.status if preparation else 'unprepared'
    error = preparation.error_code if preparation else None
    enabled = preparation.enabled if preparation else legacy
    if preparation and status == 'processing' and (preparation.heartbeat_at or preparation.started_at or utcnow()) < utcnow() - LEASE:
        status, error = 'failed', 'RAG_PROCESS_INTERRUPTED'
    if not enabled and preparation:
        status = 'disabled'
    checkpoints=db.execute(select(func.count().filter(RagPageCheckpoint.extracted.is_(True)),func.count().filter(RagPageCheckpoint.chunked.is_(True)))
        .where(RagPageCheckpoint.document_version_id==version.id,RagPageCheckpoint.pdf_page.in_(wanted))).one()
    eligible_chunks=sum(p['usable_segments'] for p in page_list)
    return {'document_version_id': version.id, 'enabled': enabled, 'legacy': legacy,
        'generation_id':preparation.generation_id if preparation else None,
        'scope_ranges':preparation.scope_ranges if preparation else [],
        'job_status':preparation.status if preparation else 'unprepared',
        'progress':dict(stage=preparation.stage if preparation else 'idle',extracted_pages=checkpoints[0],chunked_pages=checkpoints[1],
            selected_pages=len(wanted),eligible_chunks=eligible_chunks,embedded_chunks=sum(p['indexed'] for p in page_list),
            attempts=preparation.attempts if preparation else 0),
        'status': status, 'error_code': error, 'document_status': document.status,
        'counts': {name: sum(p['state'] == name for p in page_list) for name in ('automatic', 'checked', 'needs_review', 'excluded')},
        'usable_pages': sum(p['indexed'] > 0 for p in page_list), 'total_pages': version.page_count}


@router.get('/document-versions/{version_id}/rag')
def rag_state(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, document = owned_version(db, version_id, context)
    return state_output(db, version, document)


def processing(state):
    return state.status == 'queued' or (state.status == 'processing' and (state.heartbeat_at or state.started_at or utcnow()) > utcnow() - LEASE)


def begin(state):
    state.status, state.error_code = 'queued', None
    state.stage, state.lease_id, state.queued_at = 'idle', None, utcnow()
    state.generation_id, state.started_at = uuid4(), utcnow()


def prepare(version_id, generation_id, teacher_id=None):
    """Explicit worker entry point for diagnostics/tests; requests only enqueue."""
    from app.rag_worker import run_once
    return run_once(version_id,generation_id)


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
    return state_output(db, version, document)


@router.post('/document-versions/{version_id}/rag/disable')
@router.post('/document-versions/{version_id}/rag/cancel')
def disable_rag(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, document = owned_version(db, version_id, context, lock=True)
    state = db.get(RagPreparation, version.id)
    if state is None:
        state = RagPreparation(document_version_id=version.id, status='unprepared')
        db.add(state)
    state.enabled, state.generation_id = False, uuid4()
    state.status,state.stage,state.lease_id='cancelled','idle',None
    db.commit()
    return state_output(db, version, document)


@router.get('/document-versions/{version_id}/rag/pages')
def list_pages(version_id: UUID, needs_review_only: bool = False, limit: Limit = 20, offset: Offset = 0,
               context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    owned_version(db, version_id, context)
    # Page summaries first; load text only for this response's bounded page window.
    query=select(DocumentChunk.pdf_page).where(DocumentChunk.document_version_id==version_id).group_by(DocumentChunk.pdf_page)
    if needs_review_only:
        query=query.having(func.bool_or(and_(DocumentChunk.review_status=='pending',DocumentChunk.auto_eligible.is_(False))))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    numbers=list(db.scalars(query.order_by(DocumentChunk.pdf_page).limit(limit).offset(offset)))
    items=pages(db,version_id,numbers)
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset}


@router.put('/document-versions/{version_id}/rag/scope')
def save_scope(version_id: UUID,body: RagScopeInput,context: AuthContext=Depends(require_teacher),db:Session=Depends(get_db)):
    version,document=owned_version(db,version_id,context,lock=True)
    state=db.get(RagPreparation,version_id)
    if state and body.expected_generation!=state.generation_id:
        raise ApiError(409,'RAG_SCOPE_CHANGED','Nguồn đã thay đổi ở tab khác. Tải lại trước khi lưu.')
    for row in body.ranges:
        if row.page_end>version.page_count:raise ApiError(422,'PDF_PAGE_INVALID','Khoảng trang vượt PDF.')
        if row.topic_id:
            topic=db.get(Topic,row.topic_id)
            if not topic or topic.course_id!=document.course_id:raise ApiError(422,'RAG_TOPIC_INVALID','Chủ đề không thuộc học phần này.')
    if not state:
        state=RagPreparation(document_version_id=version_id,status='unprepared',enabled=False);db.add(state)
    ranges=[row.model_dump(mode='json') for row in body.ranges]
    if state.scope_ranges!=ranges:
        state.scope_ranges=ranges
        state.generation_id=uuid4()
        if state.enabled:begin(state)
    db.commit()
    return state_output(db,version,document)


@router.post('/document-versions/{version_id}/rag/retry',status_code=202)
def retry(version_id:UUID,context:AuthContext=Depends(require_teacher),db:Session=Depends(get_db)):
    version,document=owned_version(db,version_id,context,lock=True)
    state=db.get(RagPreparation,version_id)
    if not state or not state.enabled or document.status!='published':
        raise ApiError(409,'RAG_NOT_ENABLED','Công bố và cho phép nguồn trước khi thử lại.')
    if not processing(state):begin(state);db.commit()
    return state_output(db,version,document)


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
    return state_output(db, version, document)
