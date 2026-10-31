"""Hash-bound public fixture egress; no project input or automatic paid replay."""

import copy
import hashlib
import json
import asyncio
import time
import re
from uuid import UUID, NAMESPACE_URL, uuid5
import httpx
from docweave.core.identity import Actor
from docweave.db.sessions import tenant_session
from docweave.integrations.gemini import embedding_result
from docweave.integrations.groq import ranking_request, ranking_result
from docweave.integrations.provider_transport import provider_post
from docweave.rag.contracts import HostedError
from docweave.repositories import public_pilot as repository
from docweave.repositories.rag import indexing as index_repository
from docweave.rag.indexing import index_input
from docweave.rag.reranking import bounded_ranking_request


def quota_delay(headers):
    try:
        if int(headers.get("x-ratelimit-remaining-tokens", "0")) >= 7096:
            return 2.1
    except ValueError:
        pass
    value = headers.get("x-ratelimit-reset-tokens", "")
    reset = re.fullmatch(r"(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", value)
    if reset and any(reset.groups()):
        return min(3600, 60 * float(reset[1] or 0) + float(reset[2] or 0) + 1)
    return 61


def pilot_context(fixtures):
    def identity(label):
        return uuid5(NAMESPACE_URL, "docweave:public-pilot:v1:" + fixtures.dataset.corpus_manifest_sha256 + ":" + label)
    return {"actor": Actor(identity("actor"), identity("workspace")), **{key: identity(key) for key in
        ("project", "collection", "generation", "denied_workspace", "denied_project", "denied_collection", "embedding_profile", "ranking_profile")},
        "embedding_processor": "gemini:public-fixtures:v1", "ranking_processor": "groq:public-fixtures:v1",
        "documents": {meta["file"]: {**{key: identity(meta["file"] + ":" + key) for key in ("id", "version", "source", "selection")}, "hash": parsed["sha256"]} for meta, parsed in fixtures.documents()}}


async def prepare_public_pilot(engine, fixtures):
    context = pilot_context(fixtures)
    async with engine.begin() as connection:
        await repository.prepare(connection, context, fixtures.documents())
    return context


class PublicPilot:
    def __init__(self, fixtures, context, *, engine, api_keys, transport=None):
        if context != pilot_context(fixtures):
            raise HostedError("public_fixture_context_mismatch")
        self.fixtures, self.context = fixtures, copy.deepcopy(context)
        self.engine, self.api_keys, self.transport = engine, api_keys, transport
        self._next_llm_at = time.monotonic() + 61

    async def build_index(self):
        metrics = []
        c = self.context
        for meta, parsed in self.fixtures.documents():
            d = c["documents"][meta["file"]]
            snapshot = await index_input(c["actor"], d["id"], c["generation"], self.engine)
            rows = []
            started = time.perf_counter()
            if snapshot["existing_chunks"] != len(parsed["chunks"]):
                for index, span in enumerate(parsed["chunks"]):
                    vector = await self.embed_document(meta["file"], index)
                    rows.append({**span, "content": parsed["text"][span["start"]:span["end"]], "embedding": vector})
            embedding_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            async with tenant_session(self.engine, actor_id=c["actor"].user_id, workspace_id=c["actor"].workspace_id) as session:
                await index_repository.publish(session, d["id"], c["generation"], snapshot, rows, len(parsed["chunks"]))
            metrics.append({"file": meta["file"], "chunks": len(parsed["chunks"]), "created": bool(rows),
                "embedding_ms": embedding_ms, "publish_ms": (time.perf_counter() - started) * 1000})
        return metrics

    async def embed_document(self, file, chunk_index):
        payload = self.fixtures.document_request(file, chunk_index)
        result = await self._dispatch(payload, True, document=self.context["documents"][file])
        return embedding_result({"embedding": {"values": result["embedding"]}})

    async def embed_query(self, case_id):
        result = await self._dispatch(self.fixtures.query_request(case_id), True)
        return embedding_result({"embedding": {"values": result["embedding"]}})

    async def release(self, hits, *, reranked=False):
        actor = self.context["actor"]
        async with tenant_session(self.engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            await repository.authorize(session, self.context, chunk_ids=[hit["chunk_id"] for hit in hits], rerank=reranked)
        return hits

    async def rerank(self, case_id, candidates):
        if not candidates:
            return {"ordered_chunk_ids": [], "input_chunk_ids": []}
        query = self.fixtures.query_request(case_id)["content"]["parts"][0]["text"].removeprefix("task: search result | query: ")
        approved = []
        documents = {meta["file"]: parsed for meta, parsed in self.fixtures.documents()}
        for hit in candidates:
            file = hit["provenance"]["document_title"]
            if file not in documents or str(hit["document_version_id"]) != str(self.context["documents"][file]["version"]):
                raise HostedError("nonpublic_fixture_evidence")
            start, end = hit["locator"]["start"], hit["locator"]["end"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(documents[file]["text"]) or documents[file]["text"][start:end] != hit["quote"]:
                raise HostedError("nonpublic_fixture_evidence")
            approved.append({"chunk_id": str(hit["chunk_id"]), "document_version_id": str(hit["document_version_id"]), "quote": hit["quote"]})
        payload, accepted = bounded_ranking_request(query, approved)
        if payload is None:
            return {"ordered_chunk_ids": [], "input_chunk_ids": []}
        identities = [hit["chunk_id"] for hit in accepted]
        result = await self._dispatch(payload, False, chunk_ids=[UUID(value) for value in identities])
        return {"ordered_chunk_ids": result["ordered_chunk_ids"], "input_chunk_ids": identities}

    async def _dispatch(self, payload, embedding, *, document=None, chunk_ids=()):
        key = self.api_keys["gemini" if embedding else "groq"]
        if not isinstance(key, str) or not 1 <= len(key) <= 1024 or any(not 32 < ord(char) < 127 for char in key):
            raise HostedError("missing_or_invalid_api_key")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        fingerprint = hashlib.sha256(body).hexdigest()
        actor = self.context["actor"]
        async with tenant_session(self.engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            await repository.authorize(session, self.context, document=document, chunk_ids=chunk_ids, rerank=not embedding)
            operation = await repository.claim(session, self.context, fingerprint, embedding)
        result = operation["result"]
        if operation["created"]:
            try:
                if self.transport is None:
                    delay = 2.1 if embedding else max(2.1, self._next_llm_at - time.monotonic())
                    while delay > 0:
                        interval = min(delay, 30)
                        await asyncio.sleep(interval)
                        delay -= interval
                async with tenant_session(self.engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
                    await repository.authorize(session, self.context, document=document, chunk_ids=chunk_ids, rerank=not embedding)
                limits = {}
                data = await provider_post(embedding, body, key, transport=self.transport, observed_limits=limits)
                if not embedding:
                    self._next_llm_at = time.monotonic() + quota_delay(limits)
                if embedding:
                    result = {"outcome": "succeeded", "embedding": embedding_result(data)}
                else:
                    result = {"outcome": "succeeded", **ranking_result(data, [str(value) for value in chunk_ids], "openai/gpt-oss-20b")}
                    result["rate_limits"] = limits
            except (httpx.HTTPError, TimeoutError):
                result = {"outcome": "completion_unknown", "failure": "transport_uncertain"}
            except HostedError as error:
                result = {"outcome": "rejected", "failure": error.args[0]}
            async with tenant_session(self.engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
                await repository.complete_probe(session, operation["reservation"]["id"], result)
        if not result or result["outcome"] != "succeeded":
            raise HostedError("public_fixture_operation_unavailable")
        async with tenant_session(self.engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            await repository.authorize(session, self.context, document=document, chunk_ids=chunk_ids, rerank=not embedding)
        return result
