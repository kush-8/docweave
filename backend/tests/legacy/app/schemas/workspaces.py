from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, pattern=r"^[^\x00]+$", description="Trimmed, nonblank name without NUL characters.")


class WorkspaceView(BaseModel):
    id: UUID
    name: str
    role: Literal["owner", "maintainer", "member"]
    created_at: datetime


class WorkspacePage(BaseModel):
    items: list[WorkspaceView]
    next_cursor: str | None
