"""Fixed synthetic compatibility probes with a committed claim before dispatch."""

import hashlib, json, math, httpx
from uuid import UUID, NAMESPACE_URL, uuid5
from docweave.db.sessions import tenant_session
from docweave.integrations.gemini import embedding_request, embedding_result
from docweave.integrations.groq import ranking_request, ranking_result
from docweave.integrations.provider_transport import provider_post
from docweave.rag.contracts import HostedError
from docweave.rag.prompts import PROMPT_VERSION
from docweave.repositories import compatibility as repository


def synthetic_request(name):
    if name == "gemini-query":
        return embedding_request("What does synthetic error DW_SYNTH_001 mean?", "query")
    if name == "gemini-document":
        return embedding_request("Synthetic error DW_SYNTH_001 means the imaginary test connection is unavailable.", "document")
    if name not in ("groq-20b", "groq-120b"):
        raise HostedError("unknown_synthetic_probe")
    return ranking_request("What does synthetic error DW_SYNTH_001 mean?", [
        {"chunk_id": str(UUID(int=1)), "document_version_id": str(UUID(int=11)),
            "quote": "Synthetic error DW_SYNTH_001 means the imaginary test connection is unavailable."},
        {"chunk_id": str(UUID(int=2)), "document_version_id": str(UUID(int=12)),
            "quote": "The imaginary dashboard supports a blue color theme."}],
        "openai/gpt-oss-20b" if name == "groq-20b" else "openai/gpt-oss-120b")

async def prepare_synthetic_probes(engine):
    actor, workspace, project = (uuid5(NAMESPACE_URL, "docweave:synthetic-probes:v1:" + kind) for kind in ("actor", "workspace", "project"))
    operations = {}
    async with engine.begin() as connection:
        await repository.prepare_context(connection, actor, workspace, project)
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
            await repository.register_profile(connection, profile, provider, model, backend, role, input_price, output_price, incoming, outgoing)
            key = f"synthetic:{name}:{fingerprint}"
            await repository.register_request(connection, key, fingerprint, profile, incoming, outgoing)
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
        operation = await repository.claim_probe(session, operation_key, fingerprint, project_id, incoming, outgoing, model, provider, backend, role)
    if not operation["created"]:
        return operation["result"] or {"outcome": "completion_unknown", "failure": "previous_dispatch_unresolved"}
    try:
        data = await provider_post(embedding, body, api_key, transport=transport)
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
        await repository.complete_probe(session, operation["reservation"]["id"], result)
    return result
