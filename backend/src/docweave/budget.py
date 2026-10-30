"""Financial admission is separate from content policy and provider dispatch."""

import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from docweave.auth import digest
from docweave.db import tenant_session
from docweave.memberships import membership_session
from docweave.policy import require_actor, require_project_actor


class BudgetError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


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


async def budget_call(engine, actor, statement, values):
    try:
        async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            result = await session.scalar(text(statement), values)
    except DBAPIError as error:
        code = {"P0002": "not_found", "22023": "invalid_request", "DW010": "allowance_required", "DW011": "workspace_limit",
            "DW012": "application_capacity_unavailable", "DW013": "profile_unavailable", "DW014": "operation_conflict", "DW015": "settlement_conflict"}.get(getattr(error.orig, "sqlstate", None))
        if code:
            raise BudgetError(code) from None
        raise
    return Reservation.model_validate(result)


async def reserve_cost(actor, operation_key, profile_id, max_input_tokens, max_output_tokens, *, engine, project_id=None):
    if not isinstance(operation_key, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", operation_key) is None:
        raise ValueError("Use a bounded content-free operation key.")
    if any(type(value) is not int or not 0 <= value <= 1000000000 for value in (max_input_tokens, max_output_tokens)):
        raise ValueError("Token bounds must be nonnegative integers.")
    return await budget_call(engine, actor, "SELECT app.reserve_cost(:key,:profile,:input,:output,:project)",
        {"key": digest(operation_key), "profile": UUID(str(profile_id)), "input": max_input_tokens, "output": max_output_tokens,
         "project": UUID(str(project_id)) if project_id is not None else None})


async def settle_cost(reservation_id, actual_usd, execution_uncertain, *, actor, engine):
    if type(execution_uncertain) is not bool:
        raise ValueError("Execution uncertainty must be explicit.")
    if actual_usd is not None and (not isinstance(actual_usd, Decimal) or not actual_usd.is_finite() or not 0 <= actual_usd < Decimal("1000000000000")):
        raise ValueError("Actual cost must be a finite nonnegative Decimal.")
    if actual_usd is None and not execution_uncertain:
        raise ValueError("Confirmed settlement needs actual cost.")
    return await budget_call(engine, actor, "SELECT app.settle_cost(:id,:actual,:uncertain)",
        {"id": UUID(str(reservation_id)), "actual": actual_usd, "uncertain": execution_uncertain})


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


async def usage(request, actor, month, project_id=None):
    try:
        period = date(int(month[:4]), int(month[5:]), 1) if month else None
    except ValueError:
        raise HTTPException(422) from None
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        return await session.scalar(text("SELECT app.usage_report(CAST(:month AS date),:project)"), {"month": period, "project": project_id})


router = APIRouter(prefix="/api/v1", tags=["Usage"], responses={401: {"description": "Sign in required."},
    404: {"description": "Resource is missing or inaccessible."}, 422: {"description": "Invalid calendar month."}})


@router.get("/workspaces/{workspace_id}/usage", operation_id="getWorkspaceUsage", response_model=UsageReport, response_model_exclude_unset=True)
async def workspace_usage(workspace_id: UUID, request: Request, month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), actor=Depends(require_actor)):
    return await usage(request, actor, month)


@router.get("/projects/{project_id}/usage", operation_id="getProjectUsage", response_model=UsageReport, response_model_exclude_unset=True)
async def project_usage(project_id: UUID, request: Request, month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), actor=Depends(require_project_actor)):
    return await usage(request, actor, month, project_id)
