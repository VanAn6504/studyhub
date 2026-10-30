"""Private, versioned PDFs. Publication and mappings are explicit teacher actions."""
import hashlib
import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import TypeAdapter
from pypdf import PdfReader
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.courses import Limit, Offset, accessible_run, owner_course
from app.db import get_db
from app.errors import ApiError
from app.learning_models import Document, DocumentVersion, PdfFileDeletion, TopicMaterial
from app.learning_schemas import DocumentPatch, MaterialsInput
from app.models import Topic
from app.schemas import Code, Title
from app.security import AuthContext, get_auth, require_teacher
from app.rag_models import DocumentChunk, RagPreparation
from app.pdf_cleanup import cleanup_pdf_files
from app.pdf_limits import MAX_PDF_BYTES, MAX_PDF_PAGES, IO_BLOCK_BYTES

router = APIRouter(tags=['documents'])


def not_found():
    raise ApiError(404, 'RESOURCE_NOT_FOUND', 'Không tìm thấy tài nguyên học tập.')


def owner_topic(db, topic_id, teacher_id):
    topic = db.get(Topic, topic_id)
    if not topic:
        not_found()
    return topic, owner_course(db, topic.course_id, teacher_id, lock=True)


def version_access(db, version_id, course_id, published=False):
    row = db.execute(select(DocumentVersion, Document).join(Document, Document.id == DocumentVersion.document_id)
                     .where(DocumentVersion.id == version_id, Document.course_id == course_id, Document.deleted_at.is_(None), DocumentVersion.status == 'ready')).first()
    if row is None or (published and row[1].status != 'published'):
        not_found()
    return row


def version_output(version):
    return {key: getattr(version, key) for key in ('id', 'version', 'original_filename', 'sha256', 'page_count', 'byte_size', 'status', 'created_at')}


def document_output(db, document):
    return {'id': document.id, 'code': document.code, 'title': document.title, 'status': document.status,
            'document_type': document.document_type, 'show_in_learning': document.show_in_learning,
            'versions': [version_output(v) for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id, DocumentVersion.status == 'ready').order_by(DocumentVersion.version.desc()))]}


def persist_pdf(db, document, file, commit=True):
    number = (db.scalar(select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == document.id)) or 0) + 1
    storage = get_settings().pdf_storage_path
    storage.mkdir(parents=True, exist_ok=True)
    key = f'{uuid4().hex}.pdf'
    path = storage / key
    temporary = storage / (key + '.upload')
    original = re.split(r'[/\\]', file.filename or 'document.pdf')[-1]
    original = ''.join(c for c in original if c.isprintable())[:200] or 'document.pdf'
    try:
        size, digest = 0, hashlib.sha256()
        with temporary.open('xb') as target:
            while block := file.file.read(IO_BLOCK_BYTES):
                if size == 0 and not block.startswith(b'%PDF-'):
                    raise ApiError(415, 'PDF_REQUIRED', 'Tệp tải lên phải là PDF.')
                size += len(block)
                if size > MAX_PDF_BYTES:
                    raise ApiError(413, 'PDF_TOO_LARGE', 'PDF tối đa 100 MiB (104857600 byte).')
                digest.update(block)
                target.write(block)
        if not size:
            raise ApiError(415, 'PDF_REQUIRED', 'Tệp tải lên phải là PDF.')
        try:
            with temporary.open('rb') as source:
                reader = PdfReader(source, strict=True)
                if reader.is_encrypted:
                    raise ValueError('encrypted')
                pages = len(reader.pages)
                if not 1 <= pages <= MAX_PDF_PAGES:
                    raise ValueError('page limit')
                for page in reader.pages:
                    _ = page.mediabox
        except Exception:
            raise ApiError(422, 'PDF_UNREADABLE', 'PDF lỗi, mã hóa hoặc vượt giới hạn 2.000 trang.') from None
        version = DocumentVersion(document_id=document.id, version=number, storage_key=key, original_filename=original,
                                  sha256=digest.hexdigest(), page_count=pages, byte_size=size, status='ready')
        temporary.replace(path)
        db.add(version)
        db.commit() if commit else db.flush()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return version


@router.post('/courses/{course_id}/documents', status_code=201)
def upload_document(course_id: UUID, file: UploadFile, code: str = Form(...), title: str = Form(...),
                    document_type: str = Form('lecture'), show_in_learning: bool = Form(True),
                    context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    course = owner_course(db, course_id, context.user.id, lock=True)
    try:
        code, title = TypeAdapter(Code).validate_python(code), TypeAdapter(Title).validate_python(title)
    except ValueError:
        raise ApiError(422, 'DOCUMENT_METADATA_INVALID', 'Mã hoặc tên tài liệu không hợp lệ.')
    if db.scalar(select(Document.id).where(Document.course_id == course.id, Document.code == code)):
        raise ApiError(409, 'DOCUMENT_CODE_EXISTS', 'Mã tài liệu đã tồn tại. Hãy dùng mã khác hoặc chỉnh sửa tài liệu.')
    if document_type not in ('textbook', 'lecture', 'supplement'):
        raise ApiError(422, 'DOCUMENT_TYPE_INVALID', 'Loại tài liệu không hợp lệ.')
    document = Document(course_id=course.id, code=code, title=title, status='draft', document_type=document_type, show_in_learning=show_in_learning)
    db.add(document)
    db.flush()
    persist_pdf(db, document, file)
    return document_output(db, document)


@router.post('/documents/{document_id}/versions', status_code=201)
def upload_version(document_id: UUID, file: UploadFile, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    document, _ = owned_document(db, document_id, context.user.id)
    version = persist_pdf(db, document, file)
    return version_output(version)


@router.patch('/documents/{document_id}')
def patch_document(document_id: UUID, body: DocumentPatch, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    document, course = owned_document(db, document_id, context.user.id)
    if body.code and db.scalar(select(Document.id).where(Document.course_id == course.id, Document.code == body.code, Document.id != document.id)):
        raise ApiError(409, 'DOCUMENT_CODE_EXISTS', 'Mã tài liệu đã tồn tại.')
    if body.status == 'published' and not db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id == document.id, DocumentVersion.status == 'ready')):
        raise ApiError(409, 'DOCUMENT_NOT_READY', 'Tài liệu chưa có PDF hợp lệ.')
    values = body.model_dump(exclude_unset=True)
    if any(getattr(document, field) != value for field, value in values.items()):
        for field, value in values.items():
            setattr(document, field, value)
        course.content_revision += 1
        db.commit()
    return document_output(db, document)


def owned_document(db, document_id, teacher_id, include_deleted=False):
    document = db.get(Document, document_id)
    if not document:
        not_found()
    course = owner_course(db, document.course_id, teacher_id, lock=True)
    document = db.scalar(select(Document).where(Document.id == document_id).execution_options(populate_existing=True))
    if not document:
        not_found()
    if document.deleted_at and not include_deleted:
        not_found()
    return document, course


@router.delete('/documents/{document_id}', status_code=204)
def delete_document(document_id: UUID, tasks: BackgroundTasks, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    document, course = owned_document(db, document_id, context.user.id, include_deleted=True)
    remove_pdf_versions(db, list(db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id))))
    db.delete(document)
    course.content_revision += 1
    db.commit()
    tasks.add_task(cleanup_pdf_files)
    return Response(status_code=204)


def remove_pdf_versions(db, versions):
    ids = [version.id for version in versions]
    db.execute(delete(TopicMaterial).where(TopicMaterial.document_version_id.in_(ids)))
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id.in_(ids)))
    db.execute(delete(RagPreparation).where(RagPreparation.document_version_id.in_(ids)))
    for version in versions:
        if db.get(PdfFileDeletion, version.storage_key) is None:
            db.add(PdfFileDeletion(storage_key=version.storage_key))
        # Keep only version metadata for immutable quiz sources and event foreign keys.
        version.document_id, version.status = None, 'deleted'


@router.put('/documents/{document_id}/file')
def replace_document_file(document_id: UUID, tasks: BackgroundTasks, file: UploadFile,
                          code: str = Form(...), title: str = Form(...),
                          context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    document, course = owned_document(db, document_id, context.user.id)
    try:
        code, title = TypeAdapter(Code).validate_python(code), TypeAdapter(Title).validate_python(title)
    except ValueError:
        raise ApiError(422, 'DOCUMENT_METADATA_INVALID', 'Mã hoặc tên tài liệu không hợp lệ.')
    if db.scalar(select(Document.id).where(Document.course_id == course.id, Document.code == code, Document.id != document.id)):
        raise ApiError(409, 'DOCUMENT_CODE_EXISTS', 'Mã tài liệu đã tồn tại.')
    old = list(db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)))
    # Validate and write the new PDF before removing any old source or file.
    version = persist_pdf(db, document, file, commit=False)
    try:
        remove_pdf_versions(db, old)
        document.code, document.title, document.status = code, title, 'draft'
        course.content_revision += 1
        db.commit()
    except Exception:
        db.rollback()
        (get_settings().pdf_storage_path / version.storage_key).unlink(missing_ok=True)
        raise
    tasks.add_task(cleanup_pdf_files)
    return document_output(db, document)


def documents_page(db, course_id, published, limit, offset):
    query = select(Document).where(Document.course_id == course_id, Document.deleted_at.is_(None))
    if published:
        query = query.where(Document.status == 'published')
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    documents = db.scalars(query.order_by(Document.created_at, Document.id).limit(limit).offset(offset)).all()
    return {'items': [document_output(db, d) for d in documents], 'total': total, 'limit': limit, 'offset': offset}


@router.get('/courses/{course_id}/documents')
def list_course_documents(course_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    owner_course(db, course_id, context.user.id)
    return documents_page(db, course_id, False, limit, offset)


@router.get('/course-runs/{run_id}/documents')
def list_documents(run_id: UUID, limit: Limit = 20, offset: Offset = 0, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run = accessible_run(db, run_id, context)
    return documents_page(db, run.course_id, context.user.role == 'student', limit, offset)


@router.put('/topics/{topic_id}/materials')
def map_materials(topic_id: UUID, body: MaterialsInput, context: AuthContext = Depends(require_teacher), db: Session = Depends(get_db)):
    topic, course = owner_topic(db, topic_id, context.user.id)
    orders = [item.order_index for item in body.items]
    if len(orders) != len(set(orders)):
        raise ApiError(422, 'MATERIAL_ORDER_INVALID', 'Thứ tự tài liệu bị trùng.')
    for item in body.items:
        version, _ = version_access(db, item.document_version_id, course.id, published=True)
        if item.page_end < item.page_start or item.page_end > version.page_count:
            raise ApiError(422, 'PDF_PAGE_INVALID', 'Khoảng trang nằm ngoài PDF.')
    db.execute(delete(TopicMaterial).where(TopicMaterial.topic_id == topic.id))
    db.add_all([TopicMaterial(topic_id=topic.id, **item.model_dump()) for item in body.items])
    course.content_revision += 1
    db.commit()
    return {'items': materials_for_topic(db, topic.id, False)}


def materials_for_topic(db, topic_id, published=True):
    query = select(TopicMaterial, DocumentVersion, Document).join(DocumentVersion, DocumentVersion.id == TopicMaterial.document_version_id).join(Document, Document.id == DocumentVersion.document_id).where(TopicMaterial.topic_id == topic_id, Document.deleted_at.is_(None))
    if published:
        query = query.where(Document.status == 'published', DocumentVersion.status == 'ready')
    return [{'document_version_id': v.id, 'document_code': d.code, 'title': d.title, 'version': v.version,
             'page_start': m.page_start, 'page_end': m.page_end, 'page_count': v.page_count, 'order_index': m.order_index}
            for m, v, d in db.execute(query.order_by(TopicMaterial.order_index))]


@router.get('/course-runs/{run_id}/document-versions/{version_id}/content')
def pdf_content(run_id: UUID, version_id: UUID, request: Request, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    run = accessible_run(db, run_id, context)
    version, _ = version_access(db, version_id, run.course_id, published=context.user.role == 'student')
    path = get_settings().pdf_storage_path / version.storage_key
    if not path.is_file():
        raise ApiError(503, 'PDF_UNAVAILABLE', 'Tệp PDF chưa sẵn sàng.')
    # Starlette checks Range/If-Range and streams private content after authorization.
    return FileResponse(path, media_type='application/pdf', filename=version.original_filename,
                        content_disposition_type='inline', headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "sandbox"})
