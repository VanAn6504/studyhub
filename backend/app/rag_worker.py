"""PostgreSQL queue + fenced page checkpoints. One CPU job per database.

The advisory lock is session-owned, not a long Course transaction. Losing the
process releases it, so a replacement can immediately claim an interrupted job.
Every write also checks a fresh generation+lease under the Course lock.
"""
import hashlib
import re
import threading
from uuid import uuid4

import numpy as np
from pypdf import PdfReader
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.errors import ApiError
from app.learning_models import DocumentVersion
from app.models import User
from app.rag_models import DocumentChunk, RagPageCheckpoint, RagPreparation
from app.rag_policy import automatic_candidate, eligible, eligible_clause
from app.rag_scope import selected_pages
from app.security import utcnow

QUEUE_LOCK=802601030


class JobStopped(Exception):
    pass


def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        while block:=file.read(64*1024):digest.update(block)
    return digest.hexdigest()


def page_chunks(page,version_hash,version_id,number):
    from app.rag_retrieval import normalize
    flags=[]
    try:
        value=(page.extract_text() or '').replace('\x00','').strip()
        resources=page.get('/Resources',{})
        resources=resources.get_object() if hasattr(resources,'get_object') else resources
        objects=resources.get('/XObject',{})
        objects=objects.get_object() if hasattr(objects,'get_object') else objects
        if any(ref.get_object().get('/Subtype')=='/Image' for ref in objects.values()):flags.append('contains_images')
    except Exception:
        value='';flags.append('extraction_failed')
    if len(value)>30000:
        value=value[:30000];flags.append('page_text_limit')
    if len(value)<40:flags.append('short_or_empty')
    toc=bool(re.search(r'\b(table of contents|contents|agenda|muc luc)\b',normalize(value)))
    if toc:flags.append('possible_toc')
    result=[]
    for index,start in enumerate(range(0,max(1,len(value)),3000)):
        segment=value[start:start+3000]
        chunk=DocumentChunk(document_version_id=version_id,pdf_page=number,chunk_index=index,text=segment,
            source_hash=hashlib.sha256(f'{version_hash}:{number}:{index}:{segment}'.encode()).hexdigest(),
            extraction_method='pypdf',flags=flags,kind='toc' if toc else 'content',review_status='pending',revision=1)
        chunk.auto_eligible=automatic_candidate(chunk)
        result.append(chunk)
    return result


def fenced(db,version_id,generation,lease):
    from app.rag import owned_version
    from types import SimpleNamespace
    state=db.get(RagPreparation,version_id,populate_existing=True)
    if not state or not state.enabled or state.generation_id!=generation or state.lease_id!=lease or state.status!='processing':raise JobStopped()
    try:
        version,document=owned_version(db,version_id,SimpleNamespace(user=SimpleNamespace(id=state.authorized_by)),lock=True)
    except ApiError:raise JobStopped() from None
    db.refresh(state)
    if not state.enabled or state.generation_id!=generation or state.lease_id!=lease or state.status!='processing':raise JobStopped()
    teacher=db.get(User,state.authorized_by,populate_existing=True)
    if document.status!='published' or not teacher or not teacher.is_active or teacher.role!='teacher':
        state.status,state.enabled,state.error_code='cancelled',False,'RAG_SOURCE_UNAVAILABLE'
        state.lease_id=None;db.commit();raise JobStopped()
    state.heartbeat_at=utcnow()
    return state,version


def run_once(version_id=None,generation_id=None,stop=None):
    """Claim and finish one persisted job. Exposed for deterministic worker tests."""
    engine=get_engine()
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as lock:
        if not lock.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':QUEUE_LOCK}):return False
        try:
            with Session(engine,expire_on_commit=False) as db:
                query=select(RagPreparation).where(RagPreparation.enabled.is_(True),RagPreparation.status.in_(['queued','processing']))
                if version_id is not None:query=query.where(RagPreparation.document_version_id==version_id)
                state=db.scalar(query.order_by(RagPreparation.queued_at.asc().nullsfirst(),RagPreparation.document_version_id).with_for_update(skip_locked=True).limit(1))
                if not state or (generation_id is not None and state.generation_id!=generation_id):return False
                version_id,generation,lease=state.document_version_id,state.generation_id,uuid4()
                state.status,state.lease_id,state.heartbeat_at='processing',lease,utcnow()
                state.started_at=state.started_at or utcnow();state.attempts+=1;state.error_code=None
                db.commit()
            try:
                process(version_id,generation,lease,stop)
            except JobStopped:
                pass
            except Exception as error:
                with Session(engine) as db:
                    state=db.get(RagPreparation,version_id)
                    if state and state.enabled and state.generation_id==generation and state.lease_id==lease:
                        state.status='failed';state.lease_id=None
                        state.error_code=error.code if isinstance(error,ApiError) else 'RAG_PREPARATION_FAILED'
                        state.heartbeat_at=utcnow();db.commit()
            return True
        finally:
            lock.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':QUEUE_LOCK})


def process(version_id,generation,lease,stop):
    from app import rag
    engine,settings=get_engine(),get_settings()
    def interrupted():
        if stop and stop.is_set():
            with Session(engine) as db:
                state,_=fenced(db,version_id,generation,lease)
                state.status,state.lease_id='queued',None;db.commit()
            raise JobStopped()
    with Session(engine) as db:
        state,version=fenced(db,version_id,generation,lease)
        wanted=selected_pages(state.scope_ranges,version.page_count)
        path=settings.pdf_storage_path/version.storage_key
        digest,page_count=version.sha256,version.page_count
        state.stage='extracting';db.commit()
    if not path.is_file():raise ApiError(503,'PDF_UNAVAILABLE','PDF không còn sẵn sàng.')
    if file_hash(path)!=digest:raise ApiError(422,'CORPUS_UNREADABLE','Hash PDF đã thay đổi.')
    with Session(engine) as db:
        done=set(db.scalars(select(RagPageCheckpoint.pdf_page).where(RagPageCheckpoint.document_version_id==version_id,RagPageCheckpoint.chunked.is_(True))))
    missing=sorted(wanted-done)
    for start in range(0,len(missing),settings.rag_page_batch_size):
        interrupted()
        numbers=missing[start:start+settings.rag_page_batch_size]
        with Session(engine) as db:
            state,_=fenced(db,version_id,generation,lease);state.stage='extracting';db.commit()
        # Reopen for each bounded batch, releasing pypdf's resolved stream cache.
        with path.open('rb') as source:
            reader=PdfReader(source,strict=True)
            if reader.is_encrypted or len(reader.pages)!=page_count:raise ApiError(422,'CORPUS_UNREADABLE','PDF không khớp metadata.')
            prepared=[(number,page_chunks(reader.pages[number-1],digest,version_id,number)) for number in numbers]
        with Session(engine) as db:
            state,_=fenced(db,version_id,generation,lease);state.stage='chunking'
            for number,chunks in prepared:
                if db.get(RagPageCheckpoint,(version_id,number)):continue
                # A legacy extraction/manual review is immutable, never replaced.
                existing=list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_version_id==version_id,DocumentChunk.pdf_page==number)))
                if not existing:db.add_all(chunks)
                else:
                    for chunk in existing:
                        if chunk.review_status=='pending' and chunk.auto_eligible!=automatic_candidate(chunk):
                            chunk.auto_eligible=automatic_candidate(chunk);chunk.revision+=1
                db.add(RagPageCheckpoint(document_version_id=version_id,pdf_page=number))
            db.flush()
            if db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_version_id==version_id))>22000:
                raise ApiError(422,'RAG_RESOURCE_LIMIT','Nguồn vượt giới hạn xử lý; chọn khoảng trang nhỏ hơn.')
            db.commit()
    interrupted()
    # Legacy extraction/checkpoints may predate automatic opt-in. Reevaluate in
    # bounded page batches while preserving every literal teacher decision.
    numbers=sorted(wanted)
    for start in range(0,len(numbers),settings.rag_page_batch_size):
        interrupted()
        with Session(engine) as db:
            state,_=fenced(db,version_id,generation,lease)
            for chunk in db.scalars(select(DocumentChunk).where(DocumentChunk.document_version_id==version_id,
                DocumentChunk.pdf_page.in_(numbers[start:start+settings.rag_page_batch_size]),DocumentChunk.review_status=='pending')):
                candidate=automatic_candidate(chunk)
                if chunk.auto_eligible!=candidate:chunk.auto_eligible=candidate;chunk.revision+=1
            db.commit()
    encoder=rag.get_encoder(settings)
    with Session(engine) as db:
        state,_=fenced(db,version_id,generation,lease);state.embedding_code=encoder.code;db.commit()
    while True:
        interrupted()
        with Session(engine) as db:
            state,_=fenced(db,version_id,generation,lease);state.stage='embedding';db.commit()
            chunks=db.execute(select(DocumentChunk.id,DocumentChunk.source_hash,DocumentChunk.text).where(
                DocumentChunk.document_version_id==version_id,DocumentChunk.pdf_page.in_(wanted),eligible_clause(),
                or_(DocumentChunk.embedding.is_(None),DocumentChunk.embedding_code.is_(None),DocumentChunk.embedding_code!=encoder.code))
                .order_by(DocumentChunk.pdf_page,DocumentChunk.chunk_index).limit(settings.rag_embedding_batch_size)).all()
        if not chunks:break
        try:
            vectors=encoder.encode([row.text for row in chunks])
            matrix=np.asarray(vectors,dtype=np.float32)
            if matrix.shape!=(len(chunks),384) or not np.isfinite(matrix).all():raise ValueError('Invalid embedding batch')
        except Exception:
            from app.local_embeddings import unavailable
            raise unavailable() from None
        with Session(engine) as db:
            state,_=fenced(db,version_id,generation,lease)
            for row,vector in zip(chunks,vectors):
                chunk=db.get(DocumentChunk,row.id)
                if chunk and chunk.source_hash==row.source_hash and eligible(chunk):chunk.embedding,chunk.embedding_code=vector,encoder.code
            db.flush()
            state.embedded_chunks=db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_version_id==version_id,DocumentChunk.pdf_page.in_(wanted),eligible_clause(),DocumentChunk.embedding_code==encoder.code,DocumentChunk.embedding.is_not(None)))
            db.commit()
    with Session(engine) as db:
        state,_=fenced(db,version_id,generation,lease)
        # Existing extracted pages also receive automatic eligibility on opt-in.
        # This is done separately from manual reviews, which remain authoritative.
        unresolved=db.scalar(select(DocumentChunk.id).where(DocumentChunk.document_version_id==version_id,DocumentChunk.pdf_page.in_(wanted),DocumentChunk.review_status=='pending',DocumentChunk.auto_eligible.is_(False)).limit(1))
        state.status='needs_review' if unresolved else 'ready'
        state.stage,state.lease_id,state.heartbeat_at='ready',None,utcnow()
        db.commit()


class RagWorker:
    def __init__(self):
        self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self.loop,name='studyhub-rag-worker',daemon=True)
    def start(self):self.thread.start();return self
    def close(self):self.stop_event.set();self.thread.join(timeout=5)
    def loop(self):
        while not self.stop_event.is_set():
            try:worked=run_once(stop=self.stop_event)
            except Exception:worked=False # DB startup/reconnect; never log secrets.
            if not worked:self.stop_event.wait(get_settings().rag_poll_seconds)


if __name__=='__main__':
    worker=RagWorker().start()
    try:
        while worker.thread.is_alive():worker.thread.join(timeout=1)
    except KeyboardInterrupt:
        worker.close()
