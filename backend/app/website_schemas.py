"""Public responses are explicit whitelists, separate from learning payloads."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from app.schemas import DisplayName, Input, Password, Title

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Level = Literal['unspecified', 'beginner', 'intermediate', 'advanced']


class PublicationInput(Input):
    title: Title
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=400)] = ''
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=12000)] = ''
    category_code: Annotated[str, StringConstraints(max_length=64)] | None = None
    level: Level = 'unspecified'
    objectives: list[Line] = Field(default_factory=list, max_length=20)
    prerequisites: list[Line] = Field(default_factory=list, max_length=20)
    outline: list[Line] = Field(default_factory=list, max_length=100)
    material_titles: list[Line] = Field(default_factory=list, max_length=30)


class PublicMetadata(BaseModel):
    title: str
    summary: str
    description: str
    category_code: str | None
    level: Level
    objectives: list[str]
    prerequisites: list[str]
    outline: list[str]
    material_titles: list[str]


class CategoryOutput(BaseModel):
    code: str
    name: str
    course_count: int = 0


class PublicRun(BaseModel):
    id: UUID
    code: str
    instructor_name: str
    start_date: date
    timezone: str
    status: Literal['active', 'closed']
    enrollment_mode: Literal['invite_only', 'approval', 'open']
    opens_at: datetime | None
    closes_at: datetime | None
    capacity: int | None
    seats_remaining: int | None
    availability: Literal['accepting', 'full', 'closed', 'not_started', 'invite_only']
    admissions_revision: int


class PublicCourse(PublicMetadata):
    slug: str
    code: str
    category_name: str | None
    instructor_name: str
    published_at: datetime
    runs: list[PublicRun]


class PublicationOutput(BaseModel):
    course_id: UUID
    slug: str
    status: Literal['hidden', 'published']
    draft: PublicMetadata
    published: PublicMetadata | None
    published_at: datetime | None


class AdmissionsInput(Input):
    enrollment_mode: Literal['invite_only', 'approval', 'open']
    listed: bool
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    capacity: Annotated[int, Field(strict=True, ge=1, le=100000)] | None = None
    expected_revision: Annotated[int, Field(strict=True, ge=1)]

    @field_validator('opens_at', 'closes_at')
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError('Cần thời gian có múi giờ')
        return value

    @model_validator(mode='after')
    def window(self):
        if self.opens_at and self.closes_at and self.opens_at >= self.closes_at:
            raise ValueError('Thời điểm kết thúc phải sau bắt đầu')
        return self


class JoinInput(Input):
    expected_revision: Annotated[int, Field(strict=True, ge=1)]


class DecisionInput(Input):
    action: Literal['approve', 'reject']
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ''


class ProfilePatch(Input):
    display_name: DisplayName
    bio: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1200)]


class ProfileOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    display_name: str
    bio: str
    email: str
    role: Literal['student', 'teacher']


class PasswordInput(Input):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class ResumeInput(Input):
    run_id: UUID
    topic_id: UUID | None = None
    document_version_id: UUID | None = None
    view: Literal['topic', 'pdf', 'quiz', 'progress', 'results'] = 'topic'
    page: Annotated[int, Field(strict=True, ge=1, le=2000)] = 1


class ResumeOutput(BaseModel):
    run_id: UUID
    course_id: UUID
    course_title: str
    run_code: str
    topic_id: UUID | None
    document_version_id: UUID | None
    view: Literal['topic', 'pdf', 'quiz', 'progress', 'results']
    page: int
    updated_at: datetime | None
    notice: str | None = None
