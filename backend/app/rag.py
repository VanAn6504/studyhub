"""Teacher-reviewed corpus, resource-scoped chat, checked page citations."""
import hashlib
import re
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from pypdf import PdfReader
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import chat_provider
from app.config import get_settings
from app.courses import Limit, Offset, owner_course
from app.db import get_db
from app.errors import ApiError
from app.learning_models import Document, DocumentVersion
from app.models import Enrollment
from app.quizzes import student_enrollment
from app.rag_models import ChatSession, ChatTurn, DocumentChunk, RagPreparation
from app.rag_policy import eligible, eligible_clause
from app.rag_retrieval import normalize, retrieve_hybrid
from app.local_embeddings import get_encoder, unavailable as embedding_unavailable
from app.rag_schemas import ManualChunkInput, MessageInput, ReviewInput
from app.resources import not_found
from app.security import AuthContext, get_auth, require_teacher, utcnow

router = APIRouter(tags=['rag'])
INSUFFICIENT = 'Chưa có nguồn đủ chứng cứ cho câu hỏi này. Hãy đọc PDF hoặc nhờ giảng viên kiểm tra trang liên quan.'


def source_excerpt(text, quote):
    """Resolve whitespace-only quote changes to a literal span of the source.

    PDF line wraps may be flattened by Gemini. Words, case and punctuation must
    still match exactly; citations always store the original contiguous text.
    """
    parts = quote.split()
    if not parts:
        return None
    match = re.search(r'\s+'.join(re.escape(part) for part in parts), text)
    if not match or len(match.group()) > 600:
        return None
    return match.group()


def owned_version(db, version_id, context, lock=False):
    version = db.get(DocumentVersion, version_id)
    document = db.get(Document, version.document_id) if version else None
    if not document or version.status != 'ready':
        not_found()
    owner_course(db, document.course_id, context.user.id, lock=lock)
    return version, document


def chunk_output(chunk):
    return {key: getattr(chunk, key) for key in (
        'id', 'document_version_id', 'pdf_page', 'chunk_index', 'text', 'source_hash',
        'extraction_method', 'flags', 'kind', 'review_status', 'revision', 'reviewed_at', 'embedding_code', 'auto_eligible')}


def corpus_query(version_id):
    return select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)


@router.get('/document-versions/{version_id}/content')
def teacher_pdf(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, _ = owned_version(db, version_id, context)
    path = get_settings().pdf_storage_path / version.storage_key
    if not path.is_file():
        raise ApiError(503, 'PDF_UNAVAILABLE', 'Tệp PDF chưa sẵn sàng.')
    return FileResponse(path, media_type='application/pdf', filename=version.original_filename,
                        content_disposition_type='inline', headers={'Cache-Control': 'no-store', 'Content-Security-Policy': 'sandbox'})


@router.post('/document-versions/{version_id}/corpus')
def extract_corpus(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, _ = owned_version(db, version_id, context, lock=True)
    # An extracted version is never reindexed or overwritten. New PDF => new corpus.
    if db.scalar(select(DocumentChunk.id).where(DocumentChunk.document_version_id == version.id).limit(1)):
        return {'created': 0, 'status': 'already_extracted'}
    path = get_settings().pdf_storage_path / version.storage_key
    if not path.is_file():
        raise ApiError(503, 'PDF_UNAVAILABLE', 'Tệp PDF chưa sẵn sàng.')
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() != version.sha256:
            raise ValueError('Hash mismatch')
        reader = PdfReader(path, strict=True)
        if len(reader.pages) != version.page_count:
            raise ValueError('Page mismatch')
        chunks = []
        for number, page in enumerate(reader.pages, 1):
            flags = []
            try:
                text = (page.extract_text() or '').replace('\x00', '').strip()
                resources = page.get('/Resources', {})
                resources = resources.get_object() if hasattr(resources, 'get_object') else resources
                objects = resources.get('/XObject', {})
                objects = objects.get_object() if hasattr(objects, 'get_object') else objects
                if any(ref.get_object().get('/Subtype') == '/Image' for ref in objects.values()):
                    flags.append('contains_images')
            except Exception:
                text = ''
                flags.append('extraction_failed')
            if len(text) > 100_000:
                raise ValueError('Page text limit')
            if len(text) < 40:
                flags.append('short_or_empty')
            toc = bool(re.search(r'\b(table of contents|contents|agenda|muc luc)\b', normalize(text)))
            if toc:
                flags.append('possible_toc')
            for index, start in enumerate(range(0, max(1, len(text)), 3000)):
                segment = text[start:start + 3000]
                digest = hashlib.sha256(f'{version.sha256}:{number}:{index}:{segment}'.encode()).hexdigest()
                chunks.append(DocumentChunk(document_version_id=version.id, pdf_page=number, chunk_index=index,
                    text=segment, source_hash=digest, extraction_method='pypdf', flags=flags,
                    kind='toc' if toc else 'content', review_status='pending', revision=1))
                if len(chunks) > 5000:
                    raise ValueError('Corpus limit')
    except Exception:
        raise ApiError(422, 'CORPUS_UNREADABLE', 'Không thể trích PDF hoặc nội dung vượt giới hạn. Chưa ghi corpus.') from None
    db.add_all(chunks)
    db.commit()
    return {'created': len(chunks), 'status': 'pending_review'}


@router.get('/document-versions/{version_id}/chunks')
def list_chunks(version_id: UUID, pdf_page: int | None = Query(default=None, ge=1, le=500),
                limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, _ = owned_version(db, version_id, context)
    query = corpus_query(version.id)
    counts = dict(db.execute(select(DocumentChunk.review_status, func.count()).where(
        DocumentChunk.document_version_id == version.id).group_by(DocumentChunk.review_status)).all())
    if pdf_page is not None:
        query = query.where(DocumentChunk.pdf_page == pdf_page)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(DocumentChunk.pdf_page, DocumentChunk.chunk_index).limit(limit).offset(offset))
    return {'items': [chunk_output(c) for c in items], 'total': total, 'limit': limit, 'offset': offset, 'counts': counts}


@router.post('/document-versions/{version_id}/chunks', status_code=201)
def manual_chunk(version_id: UUID, body: ManualChunkInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, _ = owned_version(db, version_id, context, lock=True)
    if not db.scalar(select(DocumentChunk.id).where(DocumentChunk.document_version_id == version.id).limit(1)):
        raise ApiError(409, 'CORPUS_NOT_EXTRACTED', 'Trích văn bản PDF trước khi thêm bản phiên chép.')
    if body.pdf_page > version.page_count:
        raise ApiError(422, 'PDF_PAGE_INVALID', 'Trang nguồn nằm ngoài PDF.')
    index = (db.scalar(select(func.max(DocumentChunk.chunk_index)).where(
        DocumentChunk.document_version_id == version.id, DocumentChunk.pdf_page == body.pdf_page)))
    index = 0 if index is None else index + 1
    chunk = DocumentChunk(document_version_id=version.id, pdf_page=body.pdf_page, chunk_index=index,
        text=body.text, source_hash=hashlib.sha256(f'{version.sha256}:{body.pdf_page}:{index}:{body.text}'.encode()).hexdigest(),
        extraction_method='manual', flags=['manual_transcription'], kind='content', review_status='pending', revision=1)
    db.add(chunk)
    db.commit()
    return chunk_output(chunk)


@router.patch('/chunks/{chunk_id}')
def review_chunk(chunk_id: UUID, body: ReviewInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    chunk = db.get(DocumentChunk, chunk_id)
    if not chunk:
        not_found()
    owned_version(db, chunk.document_version_id, context, lock=True)
    db.refresh(chunk)
    if chunk.revision != body.revision:
        raise ApiError(409, 'CHUNK_REVISION_CONFLICT', 'Đoạn đã được rà soát ở tab khác. Hãy tải lại.')
    if body.review_status == 'reviewed' and len(chunk.text.strip()) < 20:
        raise ApiError(422, 'CHUNK_EMPTY', 'Đoạn thiếu văn bản. Thêm bản phiên chép đối chiếu PDF trước khi duyệt.')
    chunk.kind, chunk.review_status = body.kind, body.review_status
    chunk.auto_eligible = False
    chunk.revision += 1
    chunk.reviewed_by = context.user.id
    chunk.reviewed_at = utcnow()
    db.commit()
    return chunk_output(chunk)


@router.post('/document-versions/{version_id}/embedding-index')
def index_corpus(version_id: UUID, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    version, _ = owned_version(db, version_id, context)
    encoder = get_encoder(get_settings())
    chunks = db.scalars(corpus_query(version.id).where(eligible_clause()))
    pending = [(c.id, c.source_hash, c.text) for c in chunks if c.embedding_code != encoder.code or c.embedding is None]
    db.close()
    try:
        vectors = encoder.encode([t for _, _, t in pending])
    except Exception:
        raise embedding_unavailable() from None
    owned_version(db, version_id, context, lock=True)
    written = 0
    for (chunk_id, digest, _), vector in zip(pending, vectors):
        chunk = db.get(DocumentChunk, chunk_id, populate_existing=True)
        if chunk and chunk.source_hash == digest and eligible(chunk):
            chunk.embedding, chunk.embedding_code = vector, encoder.code
            written += 1
    db.commit()
    return {'indexed': written, 'model_code': encoder.code, 'dimension': 384}


def own_session(db, session_id, context, writing=False):
    session = db.get(ChatSession, session_id)
    enrollment = db.get(Enrollment, session.enrollment_id) if session else None
    if not enrollment or enrollment.student_id != context.user.id:
        not_found()
    run, enrollment = student_enrollment(db, enrollment.course_run_id, context, writing=writing)
    return session, run, enrollment


@router.post('/course-runs/{run_id}/chat-sessions', status_code=201)
def create_session(run_id: UUID, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _, enrollment = student_enrollment(db, run_id, context, writing=True)
    session = ChatSession(enrollment_id=enrollment.id)
    db.add(session)
    db.commit()
    return {'id': session.id, 'created_at': session.created_at}


@router.get('/course-runs/{run_id}/chat-sessions')
def list_sessions(run_id: UUID, limit: Limit = 20, offset: Offset = 0,
                  context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _, enrollment = student_enrollment(db, run_id, context)
    query = select(ChatSession).where(ChatSession.enrollment_id == enrollment.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(ChatSession.created_at.desc(), ChatSession.id).limit(limit).offset(offset))
    return {'items': [{'id': s.id, 'created_at': s.created_at} for s in items], 'total': total, 'limit': limit, 'offset': offset}


def current_sources(db, course_id):
    rows = db.execute(select(DocumentChunk, DocumentVersion, Document).join(DocumentVersion,
        DocumentVersion.id == DocumentChunk.document_version_id).join(Document, Document.id == DocumentVersion.document_id)
        .outerjoin(RagPreparation, RagPreparation.document_version_id == DocumentVersion.id)
        .where(Document.course_id == course_id, Document.status == 'published', DocumentVersion.status == 'ready',
               eligible_clause(), or_(RagPreparation.document_version_id.is_(None),
                   (RagPreparation.enabled.is_(True) & RagPreparation.status.in_(['ready', 'needs_review'])))))
    return [dict(id=str(c.id), text=c.text, pdf_page=c.pdf_page, chunk_index=c.chunk_index,
                 document_version_id=str(v.id), document_code=d.code, title=d.title, version=v.version,
                 source_hash=c.source_hash, flags=c.flags, extraction_method=c.extraction_method,
                 embedding=c.embedding, embedding_code=c.embedding_code) for c, v, d in rows]


def visible_turn(db, turn, course_id, valid=None):
    answer, status, citations = turn.answer, turn.status, turn.citations
    if citations:
        # Withdrawing a source also withdraws its stored excerpt/answer from history.
        if valid is None:
            valid = {s['id']: s for s in current_sources(db, course_id)}
        if any(c['chunk_id'] not in valid or valid[c['chunk_id']]['source_hash'] != c['source_hash'] for c in citations):
            answer, status, citations = 'Nguồn đã bị thu hồi. Câu trả lời này tạm ẩn; hãy hỏi lại sau khi nguồn được rà soát.', 'source_unavailable', []
    return {'id': turn.id, 'request_key': turn.request_key, 'question': turn.question, 'answer': answer,
            'status': status, 'citations': citations, 'model_code': turn.model_code, 'created_at': turn.created_at}


@router.get('/chat-sessions/{session_id}/messages')
def history(session_id: UUID, limit: Limit = 20, offset: Offset = 0,
            context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _, run, _ = own_session(db, session_id, context)
    query = select(ChatTurn).where(ChatTurn.chat_session_id == session_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(ChatTurn.created_at, ChatTurn.id).limit(limit).offset(offset))
    valid = {s['id']: s for s in current_sources(db, run.course_id)}
    return {'items': [visible_turn(db, t, run.course_id, valid) for t in items], 'total': total, 'limit': limit, 'offset': offset}


@router.post('/chat-sessions/{session_id}/messages')
def send_message(session_id: UUID, body: MessageInput, response: Response,
                 context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    session, run, enrollment = own_session(db, session_id, context, writing=True)
    settings = get_settings()
    now = utcnow()
    lease = now - timedelta(seconds=settings.chat_timeout_seconds + 30)
    turn = db.scalar(select(ChatTurn).where(ChatTurn.chat_session_id == session.id, ChatTurn.request_key == body.request_key))
    if turn:
        if turn.question != body.message:
            raise ApiError(409, 'CHAT_REQUEST_CONFLICT', 'ID gửi lại đã dùng cho câu hỏi khác.')
        if turn.status in {'answered', 'insufficient_sources'}:
            return visible_turn(db, turn, run.course_id)
        if turn.status == 'pending' and turn.started_at > lease:
            raise ApiError(409, 'CHAT_PENDING', 'Câu hỏi này đang được xử lý. Tải lại lịch sử sau ít giây.')
    pending = db.scalar(select(ChatTurn.id).join(ChatSession, ChatSession.id == ChatTurn.chat_session_id).where(
        ChatSession.enrollment_id == enrollment.id, ChatTurn.status == 'pending', ChatTurn.started_at > lease,
        ChatTurn.id != turn.id if turn else True).limit(1))
    if pending:
        raise ApiError(409, 'CHAT_PENDING', 'Bạn đang có một câu hỏi được xử lý. Vui lòng chờ.')
    recent = db.scalar(select(func.count()).select_from(ChatTurn).join(ChatSession, ChatSession.id == ChatTurn.chat_session_id)
        .where(ChatSession.enrollment_id == enrollment.id, ChatTurn.started_at > now - timedelta(minutes=1)))
    if recent >= 8:
        raise ApiError(429, 'CHAT_RATE_LIMIT', 'Tối đa 8 câu hỏi trong một phút. Vui lòng đợi rồi thử lại.')
    chat_provider.ensure_provider(settings)
    normalized = normalize(body.message)
    if ('dap an' in normalized or 'answer key' in normalized) and any(term in normalized for term in ('quiz', 'kiem tra', 'chua nop', 'bai thi')):
        sources = []
    else:
        sources = retrieve_hybrid(settings, body.message, current_sources(db, run.course_id))
    generation_id = uuid4()
    if not turn:
        turn = ChatTurn(chat_session_id=session.id, request_key=body.request_key, question=body.message,
                        status='pending', citations=[], generation_id=generation_id, started_at=now)
        db.add(turn)
    else:
        turn.status, turn.generation_id, turn.started_at = 'pending', generation_id, now
        turn.answer, turn.citations, turn.model_code = None, [], None
    db.commit()
    turn_id = turn.id
    # No DB locks/transaction are held while waiting for the model.
    db.close()
    try:
        generated = chat_provider.generate(settings, body.message, sources) if sources else None
        citations = []
        if generated and generated.status == 'answered':
            by_id = {s['id']: s for s in sources}
            for evidence in generated.evidence:
                source = by_id.get(str(evidence.chunk_id))
                excerpt = source_excerpt(source['text'], evidence.quote) if source else None
                if excerpt is None:
                    raise chat_provider.unavailable()
                citations.append({key: source[key] for key in (
                    'document_version_id', 'document_code', 'title', 'version', 'pdf_page', 'source_hash')} |
                    {'chunk_id': source['id'], 'excerpt': excerpt})
        answer = generated.answer if generated and generated.status == 'answered' else INSUFFICIENT
        status = 'answered' if citations else 'insufficient_sources'
    except ApiError:
        # Recheck enrollment before recording a failed request; failed retries keep the same turn.
        own_session(db, session_id, context, writing=True)
        failed = db.get(ChatTurn, turn_id, populate_existing=True)
        if failed.generation_id == generation_id:
            failed.status = 'provider_error'
            db.commit()
        raise
    _, run, _ = own_session(db, session_id, context, writing=True)
    turn = db.get(ChatTurn, turn_id, populate_existing=True)
    if turn.generation_id != generation_id:
        raise ApiError(409, 'CHAT_PENDING', 'Có lượt thử lại mới hơn. Hãy tải lại lịch sử.')
    valid = {s['id']: s for s in current_sources(db, run.course_id)}
    if any(c['chunk_id'] not in valid or c['source_hash'] != valid[c['chunk_id']]['source_hash'] for c in citations):
        citations, answer, status = [], INSUFFICIENT, 'insufficient_sources'
    turn.answer, turn.status, turn.citations = answer, status, citations
    turn.model_code = f'gemini:{settings.gemini_model}'
    db.commit()
    response.status_code = 201
    return visible_turn(db, turn, run.course_id)
