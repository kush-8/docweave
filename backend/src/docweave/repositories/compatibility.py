"""Probe persistence on caller-owned transactions; never commits or dispatches."""

import json
from decimal import Decimal
from sqlalchemy import text
from docweave.core.security import digest
from docweave.rag.contracts import HostedError


async def prepare_context(connection, actor, workspace, project):
    if await connection.scalar(text("SELECT current_user")) != "docweave_migrator":
        raise HostedError("operator_login_required")
    await connection.execute(text("SELECT app.lock_budget()"))
    await connection.execute(text("""INSERT INTO app.users(id,issuer,subject,display_name) VALUES(:id,
        'https://operator.docweave.invalid','synthetic-probes-v1','Synthetic probe operator') ON CONFLICT DO NOTHING"""), {"id": actor})
    await connection.execute(text("INSERT INTO app.workspaces(id,name) VALUES(:id,'Synthetic compatibility probes') ON CONFLICT DO NOTHING"), {"id": workspace})
    await connection.execute(text("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES(:workspace,:actor,'owner') ON CONFLICT DO NOTHING"), {"workspace": workspace, "actor": actor})
    await connection.execute(text("""INSERT INTO app.projects(id,workspace_id,name,goal) VALUES(:id,:workspace,
        'Fixed synthetic probes','Verify provider contracts using fixed synthetic content only') ON CONFLICT DO NOTHING"""), {"id": project, "workspace": workspace})
    await connection.execute(text("SELECT app.set_workspace_allowance(:workspace,NULL,0.25)"), {"workspace": workspace})

async def register_profile(connection, profile, provider, model, backend, role, input_price, output_price, incoming, outgoing):
    await connection.execute(text("""INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,
        input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,pricing_verified)
        VALUES(:id,:provider,:model,:backend,:role,'[]',:input_price,:output_price,0,:incoming,:outgoing,true) ON CONFLICT DO NOTHING"""),
        {"id": profile, "provider": provider, "model": model, "backend": backend, "role": role,
            "input_price": Decimal(input_price), "output_price": Decimal(output_price), "incoming": incoming, "outgoing": outgoing})

async def register_request(connection, key, fingerprint, profile, incoming, outgoing):
    await connection.execute(text("""INSERT INTO app.compatibility_requests(operation_hash,request_hash,profile_id,input_tokens,output_tokens)
        VALUES(:key,:request,:profile,:incoming,:outgoing) ON CONFLICT DO NOTHING"""),
        {"key": digest(key), "request": fingerprint, "profile": profile, "incoming": incoming, "outgoing": outgoing})

async def claim_probe(session, operation_key, fingerprint, project_id, incoming, outgoing, model, provider, backend, role):
    await session.execute(text("SELECT app.lock_budget()"))
    registered = (await session.execute(text("""SELECT c.request_hash,c.input_tokens,c.output_tokens,c.purpose,p.model,p.provider,p.backend,p.role
        FROM app.compatibility_requests c JOIN app.provider_profiles p ON p.id=c.profile_id WHERE c.operation_hash=:key"""),
        {"key": digest(operation_key)})).mappings().one_or_none()
    if registered is None or tuple(registered[key] for key in ("request_hash", "input_tokens", "output_tokens", "purpose", "model", "provider", "backend", "role")) != (fingerprint, incoming, outgoing, "synthetic", model, provider, backend, role):
        raise HostedError("probe_configuration_mismatch")
    operation = await session.scalar(text("SELECT app.claim_compatibility_probe(:key,:request,:project)"),
        {"key": digest(operation_key), "request": fingerprint, "project": project_id})
    return operation

async def complete_probe(session, operation_id, result):
    await session.execute(text("SELECT app.complete_compatibility_probe(:id,CAST(:result AS jsonb),NULL,true)"),
        {"id": operation_id, "result": json.dumps(result)})

async def retained_cost(connection, workspace_id):
    return await connection.scalar(text("SELECT coalesce(sum(charged_usd),0) FROM app.cost_reservations WHERE workspace_id=:workspace"), {"workspace": workspace_id})
