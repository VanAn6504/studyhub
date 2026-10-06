from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator
from app.schemas import Input

ChunkText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=3500)]


class ManualChunkInput(Input):
    pdf_page: Annotated[int, Field(strict=True, ge=1, le=500)]
    text: ChunkText


class ReviewInput(Input):
    revision: Annotated[int, Field(strict=True, ge=1)]
    review_status: Literal['pending', 'reviewed', 'rejected']
    kind: Literal['content', 'cover', 'toc', 'image']

    @model_validator(mode='after')
    def content_only(self):
        if self.review_status == 'reviewed' and self.kind != 'content':
            raise ValueError('Chỉ duyệt đoạn nội dung; không dùng bìa, mục lục hoặc ảnh chưa phiên chép')
        return self


class MessageInput(Input):
    request_key: UUID
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class Evidence(Input):
    chunk_id: UUID
    quote: Annotated[str, StringConstraints(strip_whitespace=True, min_length=15, max_length=600)]


class GeneratedAnswer(Input):
    status: Literal['answered', 'insufficient_sources']
    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    evidence: Annotated[list[Evidence], Field(max_length=4)]

    @model_validator(mode='after')
    def evidence_required(self):
        if (self.status == 'answered') != bool(self.evidence):
            raise ValueError('Câu trả lời phải có chứng cứ; từ chối phải không có chứng cứ')
        return self
