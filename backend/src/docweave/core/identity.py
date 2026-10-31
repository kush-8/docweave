from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    workspace_id: UUID
