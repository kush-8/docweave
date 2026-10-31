from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel


class Reservation(BaseModel):
    id: UUID
    workspace_id: UUID
    actor_id: UUID
    project_id: UUID | None
    profile_id: UUID
    month: date
    maximum_usd: Decimal
    actual_usd: Decimal | None
    charged_usd: Decimal
    status: Literal["reserved", "uncertain", "metered"]
    created: bool


class UsageReport(BaseModel):
    workspace_id: UUID
    project_id: UUID | None = None
    month: str
    timezone: Literal["Asia/Calcutta"]
    metered_usd: str
    reserved_usd: str
    retained_uncertain_usd: str
    workspace_allowance_usd: str | None
    capacity_status: Literal["available", "allowance_required", "workspace_limit", "application_capacity_unavailable"]
