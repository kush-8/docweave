"""Operator-only fixed synthetic probes; never accepts project text or arbitrary URLs."""

import asyncio
import hashlib
import json
import math
import argparse
import os
from decimal import Decimal
from datetime import datetime, UTC
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from dotenv import dotenv_values
from sqlalchemy import text

from docweave.auth import digest
from docweave.db import tenant_session
from docweave.hosted import HostedError, PROMPT_VERSION, embedding_result, ranking_result, synthetic_request, unique_keys
from docweave.settings import database_url


async def prepare_synthetic_probes(engine):
    actor, workspace, project = (uuid5(NAMESPACE_URL, "docweave:synthetic-probes:v1:" + kind) for kind in ("actor", "workspace", "project"))
    operations = {}
    async with engine.begin() as connection:
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
        for name in ("gemini-query", "gemini-document", "groq-20b", "groq-120b"):
            payload = synthetic_request(name)
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            embedding = name.startswith("gemini-")
            model = "gemini-embedding-2" if embedding else payload["model"]
            provider = "gemini" if embedding else "groq"
            backend = "google-generativelanguage" if embedding else "groq-cloud"
            role = "embedding" if embedding else "reranking" if name == "groq-20b" else "generation"
            incoming, outgoing = (8192, 0) if embedding else (131072, 4096)
            input_price, output_price = ("0.20", "0") if embedding else ("0.075", "0.30") if name == "groq-20b" else ("0.15", "0.60")
            profile = uuid5(NAMESPACE_URL, f"docweave:synthetic-profile:v1:{model}:{input_price}:{output_price}:{incoming}:{outgoing}")
            await connection.execute(text("""INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,
                input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,pricing_verified)
                VALUES(:id,:provider,:model,:backend,:role,'[]',:input_price,:output_price,0,:incoming,:outgoing,true) ON CONFLICT DO NOTHING"""),
                {"id": profile, "provider": provider, "model": model, "backend": backend, "role": role,
                    "input_price": Decimal(input_price), "output_price": Decimal(output_price), "incoming": incoming, "outgoing": outgoing})
            key = f"synthetic:{name}:{fingerprint}"
            await connection.execute(text("""INSERT INTO app.compatibility_requests(operation_hash,request_hash,profile_id,input_tokens,output_tokens)
                VALUES(:key,:request,:profile,:incoming,:outgoing) ON CONFLICT DO NOTHING"""),
                {"key": digest(key), "request": fingerprint, "profile": profile, "incoming": incoming, "outgoing": outgoing})
            operations[name] = key
    return {"actor_id": str(actor), "workspace_id": str(workspace), "project_id": str(project), "operations": operations}


async def run_synthetic_probe(actor, project_id, name, operation_key, *, engine, api_key, transport=None):
    payload = synthetic_request(name)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    fingerprint = hashlib.sha256(body).hexdigest()
    embedding = name.startswith("gemini-")
    model = "gemini-embedding-2" if embedding else payload["model"]
    provider = "gemini" if embedding else "groq"
    backend = "google-generativelanguage" if embedding else "groq-cloud"
    role = "embedding" if embedding else "reranking" if name == "groq-20b" else "generation"
    incoming, outgoing = (8192, 0) if embedding else (131072, 4096)
    if not isinstance(api_key, str) or not 1 <= len(api_key) <= 1024 or any(not 32 < ord(char) < 127 for char in api_key):
        raise HostedError("missing_or_invalid_api_key")
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        await session.execute(text("SELECT app.lock_budget()"))
        registered = (await session.execute(text("""SELECT c.request_hash,c.input_tokens,c.output_tokens,p.model,p.provider,p.backend,p.role
            FROM app.compatibility_requests c JOIN app.provider_profiles p ON p.id=c.profile_id WHERE c.operation_hash=:key"""),
            {"key": digest(operation_key)})).mappings().one_or_none()
        if registered is None or tuple(registered[key] for key in ("request_hash", "input_tokens", "output_tokens", "model", "provider", "backend", "role")) != (fingerprint, incoming, outgoing, model, provider, backend, role):
            raise HostedError("probe_configuration_mismatch")
        operation = await session.scalar(text("SELECT app.claim_compatibility_probe(:key,:request,:project)"),
            {"key": digest(operation_key), "request": fingerprint, "project": project_id})
    if not operation["created"]:
        return operation["result"] or {"outcome": "completion_unknown", "failure": "previous_dispatch_unresolved"}
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent" if embedding else "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity", **({"x-goog-api-key": api_key} if embedding else {"Authorization": "Bearer " + api_key})}
    try:
        async with asyncio.timeout(45), httpx.AsyncClient(transport=transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False),
            timeout=httpx.Timeout(20, connect=5), trust_env=False, follow_redirects=False) as client:
            async with client.stream("POST", url, content=body, headers=headers) as response:
                if response.status_code != 200:
                    raise HostedError("provider_http_" + str(response.status_code))
                if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
                    raise HostedError("provider_response_encoding")
                response_body = bytearray()
                async for chunk in response.aiter_bytes(8192):
                    response_body.extend(chunk)
                    if len(response_body) > 131072:
                        raise HostedError("provider_response_too_large")
        try:
            data = json.loads(response_body, object_pairs_hook=unique_keys)
        except (ValueError, UnicodeError):
            raise HostedError("invalid_provider_json") from None
        if embedding:
            values = embedding_result(data)
            result = {"outcome": "succeeded", "dimensions": len(values), "norm": math.sqrt(sum(value * value for value in values)),
                "vector_sha256": hashlib.sha256(json.dumps(values).encode()).hexdigest()}
        else:
            identities = [candidate["chunk_id"] for candidate in json.loads(payload["messages"][1]["content"])["evidence"]]
            validated = ranking_result(data, identities, model)
            if validated["ordered_chunk_ids"] != identities[:1]:
                raise HostedError("synthetic_ranking_incorrect")
            result = {"outcome": "succeeded", **validated, "prompt_version": PROMPT_VERSION}
    except (httpx.HTTPError, TimeoutError):
        result = {"outcome": "completion_unknown", "failure": "transport_uncertain"}
    except HostedError as error:
        result = {"outcome": "rejected", "failure": error.args[0]}
    # Advertised usage is not verified billing; retain the full reservation until reconciliation.
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        await session.execute(text("SELECT app.complete_compatibility_probe(:id,CAST(:result AS jsonb),NULL,true)"),
            {"id": operation["reservation"]["id"], "result": json.dumps(result)})
    return result


def operator_url():
    url = database_url("MIGRATION_DATABASE_URL")
    if (url.host, url.port, url.database, url.username) != ("127.0.0.1", 55432, "docweave", "docweave_migrator") or url.query:
        raise HostedError("development_operator_target_required")
    return url


async def main(run):
    from uuid import UUID
    from docweave.db import make_engine
    from docweave.evaluation import write_report
    from docweave.policy import Actor

    engine = make_engine(operator_url())
    root = Path(__file__).resolve().parents[3]
    try:
        values = dotenv_values(root / ".env")
        keys = {provider: os.environ.get(provider.upper() + "_API_KEY", values.get(provider.upper() + "_API_KEY")) for provider in ("gemini", "groq")}
        if run and not all(keys.values()):
            raise HostedError("missing_api_keys")
        configuration = await prepare_synthetic_probes(engine)
        if not run:
            return {"prepared": True, "inference_dispatched": False, **configuration}
        actor = Actor(UUID(configuration["actor_id"]), UUID(configuration["workspace_id"]))
        results = {}
        for name, key in configuration["operations"].items():
            results[name] = await run_synthetic_probe(actor, UUID(configuration["project_id"]), name, key,
                engine=engine, api_key=keys["gemini" if name.startswith("gemini-") else "groq"])
        async with engine.connect() as connection:
            retained = await connection.scalar(text("SELECT coalesce(sum(charged_usd),0) FROM app.cost_reservations WHERE workspace_id=:workspace"), {"workspace": actor.workspace_id})
        report = {"version": "synthetic-compatibility-v1", "created_at": datetime.now(UTC).isoformat(),
            "billing_verified": False, "private_processing_enabled": False, "retained_usd": str(retained), "results": results}
        write_report(root / "backend/eval/reports/compatibility-v1.json", report)
        return report
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare fixed synthetic probes; --run dispatches only unclaimed requests under the durable US$0.25 cap.")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(main(args.run)), indent=2))
    except HostedError as error:
        parser.exit(1, f"Synthetic probe failed: {error}\n")
