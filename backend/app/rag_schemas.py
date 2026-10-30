from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator
from app.schemas import Input

ChunkText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=3500)]


class ManualChunkInput(Input):
    pdf_page: Annotated[int, Field(strict=True, ge=1, le=2000)]
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


class PageReviewInput(Input):
    revision: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
    action: Literal['allow', 'exclude']
    transcription: ChunkText | None = None

    @model_validator(mode='after')
    def transcription_only_when_allowed(self):
        if self.transcription is not None and self.action != 'allow':
            raise ValueError('Chỉ thêm phiên chép khi cho phép trang')
        return self


class MessageInput(Input):
    request_key: UUID
    topic_id: UUID | None = None
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class RagRange(Input):
    page_start: Annotated[int, Field(strict=True, ge=1, le=2000)]
    page_end: Annotated[int, Field(strict=True, ge=1, le=2000)]
    topic_id: UUID | None = None
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ''

    @model_validator(mode='after')
    def ordered(self):
        if self.page_end<self.page_start:raise ValueError('Khoảng trang ngược')
        return self


class RagScopeInput(Input):
    ranges: Annotated[list[RagRange],Field(max_length=100)] = []
    expected_generation: UUID | None = None


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
