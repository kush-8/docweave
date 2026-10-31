from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from docweave.schemas.common import StrictInput, Nonblank, ContextText


class StackEntry(StrictInput):
    technology: Nonblank
    docs_target: Nonblank | None = None


class ProjectCreate(StrictInput):
    model_config = ConfigDict(json_schema_extra={"oneOf": [
        {"required": ["stack"], "not": {"required": ["stack_review_id"]}},
        {"required": ["stack_review_id"], "not": {"required": ["stack"]}},
    ]})
    name: Nonblank
    goal: Nonblank
    stack: list[StackEntry] | None = Field(None, min_length=1)
    stack_review_id: UUID | None = None
    architecture_notes: ContextText = ""
    environment: ContextText = ""
    constraints: ContextText = ""

    @model_validator(mode="after")
    def one_stack(self):
        if (self.stack is None) == (self.stack_review_id is None):
            raise ValueError("Provide exactly one manual stack or confirmed review.")
        return self


class ProjectPatch(StrictInput):
    model_config = ConfigDict(json_schema_extra={"minProperties": 2})
    expected_revision: int = Field(ge=1, le=2147483647, strict=True)
    name: Nonblank | None = None
    goal: Nonblank | None = None
    stack: list[StackEntry] | None = Field(None, min_length=1)
    architecture_notes: ContextText | None = None
    environment: ContextText | None = None
    constraints: ContextText | None = None

    @model_validator(mode="after")
    def has_change(self):
        if len(self.model_fields_set) < 2:
            raise ValueError("Provide at least one field to edit.")
        return self


class ProjectDependency(BaseModel):
    id: UUID
    technology: str
    declared_version: str | None
    resolved_version: str | None
    docs_target: str | None


class ProjectView(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    goal: str
    stack: list[ProjectDependency]
    context_revision: int
    default_collection_id: UUID
    # shortcut: derive live source status when source approval/import workers are implemented.
    source_state: Literal["pending_review"]
    architecture_notes: str
    environment: str
    constraints: str


class ProjectCreated(BaseModel):
    project: ProjectView
    job_ids: list[UUID]
    pending_dependency_ids: list[UUID]


class ProjectPage(BaseModel):
    items: list[ProjectView]
    next_cursor: str | None
