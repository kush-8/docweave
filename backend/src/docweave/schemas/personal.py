from uuid import UUID
from pydantic import Field, field_validator
from docweave.schemas.common import StrictInput, Nonblank, ContextText

class RepositorySetup(StrictInput):
    repository_id: int = Field(gt=0,le=999999999999999999,strict=True)
    branch: str = Field(default='',max_length=255)
    application_path: str = Field(default='',max_length=512)
    goal: Nonblank = Field(max_length=4000)
    architecture_notes: ContextText = Field(default='',max_length=16000)
    environment: ContextText = Field(default='',max_length=4000)
    constraints: ContextText = Field(default='',max_length=8000)

    @field_validator('application_path')
    @classmethod
    def safe_path(cls,value):
        if value and (value.startswith('/') or '\\' in value or ':' in value or any(part in ('','..','.') for part in value.split('/'))):
            raise ValueError('Choose a repository-relative application folder')
        return value

    @field_validator('branch')
    @classmethod
    def safe_branch(cls,value):
        if any(ord(c)<32 for c in value) or '\x00' in value:
            raise ValueError('Invalid branch')
        return value

class PersonalProjectCreate(RepositorySetup):
    name: str = Field(default='',max_length=200)

class ConversationCreate(StrictInput):
    answer_profile_id: UUID | None = None

class TurnCreate(StrictInput):
    message: Nonblank = Field(max_length=16000)
    idempotency_key: UUID

class ProcessingPolicyInput(StrictInput):
    expected_revision:int=Field(ge=1,strict=True)
    approved_processor_ids:list[str]=Field(max_length=50)

class DocumentReviewInput(StrictInput):
    document_version_id:UUID
    content_hash:str=Field(pattern='^[0-9a-f]{64}$')
    rule_revision:Nonblank=Field(max_length=100)


class DocumentationChoiceInput(StrictInput):
    expected_revision: int = Field(ge=1, strict=True)
    revision_id: UUID | None = None
    accept_fallback: bool = Field(default=False, strict=True)
