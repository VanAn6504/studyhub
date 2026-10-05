from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator
from app.schemas import Code, Input, Title

TextBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
PageNumber = Annotated[int, Field(strict=True, ge=1, le=500)]


class DocumentPatch(Input):
    title: Title | None = None
    status: Literal['draft', 'published', 'archived'] | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Cần trường cập nhật không null')
        return self


class Material(Input):
    document_version_id: UUID
    page_start: PageNumber
    page_end: PageNumber
    order_index: Annotated[int, Field(strict=True, ge=1, le=100)]


class MaterialsInput(Input):
    items: Annotated[list[Material], Field(max_length=100)]


class Source(Input):
    document_version_id: UUID
    pdf_page: PageNumber


class QuestionContent(Input):
    stem: TextBody
    options: dict[Literal['A', 'B', 'C', 'D'], Title]
    correct_option: Literal['A', 'B', 'C', 'D']
    explanation: TextBody
    sources: Annotated[list[Source], Field(min_length=1, max_length=20)]

    @field_validator('options')
    @classmethod
    def four_options(cls, value):
        if set(value) != {'A', 'B', 'C', 'D'}:
            raise ValueError('Cần đủ A-D')
        return value


class QuestionInput(QuestionContent):
    code: Code


class QuizInput(Input):
    question_version_ids: Annotated[list[UUID], Field(min_length=3, max_length=100)]

    @field_validator('question_version_ids')
    @classmethod
    def unique_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Câu hỏi trùng')
        return value


class BeginInput(Input):
    published_quiz_version_id: UUID
    request_key: UUID


class Answer(Input):
    quiz_version_item_id: UUID
    selected_option: Literal['A', 'B', 'C', 'D'] | None


class AnswersInput(Input):
    expected_revision: Annotated[int, Field(strict=True, ge=0)]
    answers: Annotated[list[Answer], Field(max_length=100)]


class SubmitInput(Input):
    expected_revision: Annotated[int, Field(strict=True, ge=0)]


class EventInput(Input):
    client_event_id: UUID
    viewer_session_id: UUID
    type: Literal['document_open', 'page_view']
    document_version_id: UUID
    pdf_page: PageNumber | None = None
    client_observed_at: datetime | None = None

    @model_validator(mode='after')
    def valid_type(self):
        if (self.type == 'page_view') != (self.pdf_page is not None):
            raise ValueError('Trang không khớp loại sự kiện')
        if self.client_observed_at is not None and self.client_observed_at.tzinfo is None:
            raise ValueError('Timestamp cần timezone')
        return self


class EventsInput(Input):
    schema_version: Literal['learning_event_v1']
    events: Annotated[list[EventInput], Field(min_length=1, max_length=50)]
