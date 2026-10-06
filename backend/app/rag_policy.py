"""Automatic eligibility is distinct from a teacher's literal page review."""
from sqlalchemy import and_, or_
from app.rag_models import DocumentChunk


def eligible_clause():
    return and_(DocumentChunk.kind == 'content', or_(DocumentChunk.review_status == 'reviewed',
        and_(DocumentChunk.review_status == 'pending', DocumentChunk.auto_eligible.is_(True))))


def eligible(chunk):
    return chunk.kind == 'content' and (chunk.review_status == 'reviewed' or
        chunk.review_status == 'pending' and chunk.auto_eligible)


def issues(chunk):
    result = list(chunk.flags)
    if chunk.pdf_page == 1 and chunk.extraction_method == 'pypdf':
        result.append('possible_cover')
    if len(chunk.text.strip()) < 40 and 'short_or_empty' not in result:
        result.append('short_or_empty')
    if chunk.kind != 'content':
        result.append('excluded_kind')
    return sorted(set(result))


def automatic_candidate(chunk):
    # An image (including a slide logo) does not invalidate extracted text.
    # Retrieval rejects code questions on image sources without transcription.
    blocking = [flag for flag in issues(chunk) if flag != 'contains_images']
    return chunk.extraction_method == 'pypdf' and chunk.reviewed_by is None and not blocking
