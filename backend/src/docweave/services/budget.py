import re
from decimal import Decimal
from uuid import UUID
from docweave.core.errors import BudgetError
from docweave.core.security import digest
from docweave.db.sessions import budget_session
from docweave.repositories import budget as repository
from docweave.schemas.budget import Reservation


async def budget_call(engine, actor, operation, values):
    async with budget_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        result = await operation(session, values)
    return Reservation.model_validate(result)


async def reserve_cost(actor, operation_key, profile_id, max_input_tokens, max_output_tokens, *, engine, project_id=None):
    if not isinstance(operation_key, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", operation_key) is None:
        raise ValueError("Use a bounded content-free operation key.")
    if any(type(value) is not int or not 0 <= value <= 1000000000 for value in (max_input_tokens, max_output_tokens)):
        raise ValueError("Token bounds must be nonnegative integers.")
    return await budget_call(engine, actor, repository.reserve_cost,
        {"key": digest(operation_key), "profile": UUID(str(profile_id)), "input": max_input_tokens, "output": max_output_tokens,
         "project": UUID(str(project_id)) if project_id is not None else None})


async def settle_cost(reservation_id, actual_usd, execution_uncertain, *, actor, engine):
    if type(execution_uncertain) is not bool:
        raise ValueError("Execution uncertainty must be explicit.")
    if actual_usd is not None and (not isinstance(actual_usd, Decimal) or not actual_usd.is_finite() or not 0 <= actual_usd < Decimal("1000000000000")):
        raise ValueError("Actual cost must be a finite nonnegative Decimal.")
    if actual_usd is None and not execution_uncertain:
        raise ValueError("Confirmed settlement needs actual cost.")
    return await budget_call(engine, actor, repository.settle_cost,
        {"id": UUID(str(reservation_id)), "actual": actual_usd, "uncertain": execution_uncertain})
