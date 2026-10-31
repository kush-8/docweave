from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field


class ProcessorView(BaseModel):
    id: str
    provider: Literal["gemini", "groq", "huggingface"]
    backend: str
    roles: list[str]


class ProviderProfileView(BaseModel):
    id: UUID
    provider: Literal["gemini", "groq", "huggingface"]
    model: str
    backend: str
    enabled: bool
    disabled_reason: str | None = Field(None, exclude_if=lambda value: value is None)
    processors: list[ProcessorView]


class ProviderPage(BaseModel):
    items: list[ProviderProfileView]
    next_cursor: str | None
