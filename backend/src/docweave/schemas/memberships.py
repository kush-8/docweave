from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


Role = Literal["owner", "maintainer", "member"]


class MemberRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class InvitationInput(MemberRole):
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def address_only(cls, value):
        if isinstance(value, str) and ("<" in value or ">" in value):
            raise ValueError("Use an email address without a display name.")
        return value


class MemberView(BaseModel):
    workspace_id: UUID
    user_id: UUID
    role: Role
    display_name: str


class InvitationView(BaseModel):
    id: UUID
    workspace_id: UUID
    email: EmailStr
    role: Role
    expires_at: datetime
    status: Literal["pending", "accepted", "expired", "revoked"]


class InvitationCreated(BaseModel):
    invitation: InvitationView
    acceptance_url: str


class MemberPage(BaseModel):
    items: list[MemberView]
    next_cursor: str | None


class InvitationPage(BaseModel):
    items: list[InvitationView]
    next_cursor: str | None
