from uuid import UUID
from pydantic import BaseModel
from docweave.schemas.common import StrictInput


class DocumentView(BaseModel):
    id: UUID
    collection_id: UUID
    title: str
    media_type: str
    status: str
    malware_scan: str = "disabled"
    active_version_id: UUID | None = None


class DocumentPage(BaseModel):
    items: list[DocumentView]
    next_cursor: str | None


class ImportInput(StrictInput):
    source_selection_id: UUID
    collection_id: UUID
