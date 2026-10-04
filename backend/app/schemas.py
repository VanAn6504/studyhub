from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterInput(EmailInput):
    password: Password
    display_name: DisplayName


class LoginInput(EmailInput):
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class UserOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str
    role: Literal["teacher", "student"]


class AuthOutput(BaseModel):
    user: UserOutput
    csrf_token: str


class CourseInput(Input):
    code: Code
    title: Title


class CourseOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    title: str
    owner_teacher_id: UUID
    content_revision: int
    created_at: datetime


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Múi giờ IANA không hợp lệ")
    return value


class RunInput(Input):
    code: Code
    course_run_start_date: date
    timezone: str = "Asia/Bangkok"
    _timezone = field_validator("timezone")(validate_timezone)


class RunPatch(Input):
    status: Literal["draft", "active", "closed"] | None = None
    course_run_start_date: date | None = None
    timezone: str | None = None

    @model_validator(mode="after")
    def check_patch(self):
        if not self.model_fields_set:
            raise ValueError("Cần ít nhất một trường để cập nhật")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Trường cập nhật không được null")
        if self.timezone is not None:
            validate_timezone(self.timezone)
        return self


class RunOutput(BaseModel):
    id: UUID
    code: str
    course_id: UUID
    course_title: str
    course_run_start_date: date
    timezone: str
    status: Literal["draft", "active", "closed"]
    data_origin: Literal["real", "synthetic"]
    student_count: int


class EnrollmentInput(Input):
    student_email: EmailStr

    @field_validator("student_email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class EnrollmentPatch(Input):
    status: Literal["active", "inactive"]


class EnrollmentOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    course_run_id: UUID
    student_id: UUID
    status: Literal["active", "inactive"]
    enrolled_at: datetime


class TopicInput(Input):
    code: Code
    title: Title
    order_index: Annotated[int, Field(strict=True, ge=1, le=1000)]
    objectives: Annotated[list[Title], Field(max_length=20)]


class PrerequisitesInput(Input):
    prerequisite_topic_ids: Annotated[list[UUID], Field(max_length=100)]

    @field_validator("prerequisite_topic_ids")
    @classmethod
    def unique_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Danh sách chủ đề tiên quyết có ID trùng")
        return values


class TopicOutput(BaseModel):
    id: UUID
    code: str
    title: str
    order_index: int
    objectives: list[str]
    prerequisite_topic_ids: list[UUID]
    materials: list = Field(default_factory=list)
    quiz: None = None


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
