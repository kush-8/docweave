from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from docweave.schemas.common import Nonblank, StrictInput


Revision = Annotated[int, Field(ge=1, le=2147483647, strict=True)]


class CollectionCreate(StrictInput):
    name: Nonblank


class Grant(StrictInput):
    user_id: UUID
    access: Literal["read", "write"]


class GrantSetInput(StrictInput):
    expected_revision: Revision
    grants: list[Grant]

    @model_validator(mode="after")
    def unique_members(self):
        if len({grant.user_id for grant in self.grants}) != len(self.grants):
            raise ValueError("One grant per member is allowed.")
        return self


class ProcessingPolicyInput(StrictInput):
    expected_revision: Revision
    approved_processor_ids: list[Nonblank] = Field(json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def unique_processors(self):
        if len(set(self.approved_processor_ids)) != len(self.approved_processor_ids):
            raise ValueError("Processor IDs must be unique.")
        return self


class CollectionView(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    can_write: bool


class CollectionPage(BaseModel):
    items: list[CollectionView]
    next_cursor: str | None


class GrantSet(BaseModel):
    revision: int
    grants: list[Grant]


class ProcessingPolicy(BaseModel):
    revision: int
    approved_processor_ids: list[str]
