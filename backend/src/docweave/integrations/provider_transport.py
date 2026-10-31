"""One bounded provider HTTP request; durable admission belongs to its caller."""

import asyncio, json, httpx
from docweave.rag.contracts import HostedError, unique_keys


async def provider_post(embedding, body, api_key, *, transport=None):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent" if embedding else "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity", **({"x-goog-api-key": api_key} if embedding else {"Authorization": "Bearer " + api_key})}
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
    return data
