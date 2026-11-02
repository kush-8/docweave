"""Read-only GitHub App user-token transport. Never elevate to installation authority."""
import base64
import hashlib
import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode

import httpx2
from docweave.core.errors import DomainError


_request_budget = ContextVar("github_request_budget", default=None)
METADATA_NAMES = frozenset(("requirements.txt", "pyproject.toml", "uv.lock", "package.json",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Pipfile", "Pipfile.lock", "pnpm-workspace.yaml"))


def safe_path(path):
    return isinstance(path, str) and bool(path) and not path.startswith("/") and "\\" not in path and ":" not in path and all(part not in ("", ".", "..") for part in path.split("/"))


def metadata_path(path):
    return safe_path(path) and not set(PurePosixPath(path).parts[:-1]) & {
        'node_modules', 'vendor', '.venv', 'venv', '.git', '.hg', '.svn', '.yarn',
        '.pnpm-store', 'dist', 'build', '.next', '.nuxt', '__pycache__', '.tox',
    } and (PurePosixPath(path).name in METADATA_NAMES or path.endswith((".txt", ".in")))


def valid_sha(sha):
    return isinstance(sha, str) and len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)


def validate_user(data):
    if not isinstance(data, dict) or type(data.get("id")) is not int or data["id"] <= 0 or not isinstance(data.get("login"), str) or not data["login"].strip():
        raise DomainError("invalid_auth")
    name = data.get("name")
    return {"id": data["id"], "login": data["login"], "name": name if isinstance(name, str) and name.strip() else data["login"]}


class GitHubClient:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.transport = transport

    @contextmanager
    def request_budget(self, limit):
        saved = _request_budget.set(limit)
        try:
            yield
        finally:
            _request_budget.reset(saved)

    def authorize_url(self, state, verifier):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return "https://github.com/login/oauth/authorize?" + urlencode({"client_id": self.settings.client_id,
            "redirect_uri": self.settings.callback, "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})

    async def _request(self, method, path, *, token=None, data=None, params=None):
        remaining = _request_budget.get()
        if remaining is not None:
            if remaining <= 0:
                raise DomainError("not_ready")
            _request_budget.set(remaining - 1)
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = "Bearer " + token
        url = "https://github.com/login/oauth/access_token" if data is not None else "https://api.github.com" + path
        if data is not None:
            headers["Accept"] = "application/json"
        try:
            async with httpx2.AsyncClient(timeout=10, trust_env=False, follow_redirects=False, transport=self.transport) as client:
                async with client.stream(method, url, headers=headers, data=data, params=params) as response:
                    failures = {401: "unauthenticated", 404: "not_found", 403: "forbidden"}
                    if response.status_code != 200:
                        raise DomainError(failures.get(response.status_code, "not_ready"))
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 16 * 1024 * 1024:
                            raise DomainError("not_ready")
            result = json.loads(body)
            if isinstance(result, dict) and "error" in result:
                raise DomainError("invalid_auth")
            return result
        except (httpx2.HTTPError, ValueError, TypeError):
            raise DomainError("not_ready") from None

    async def _token(self, values):
        data = await self._request("POST", "", data={"client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret, **values})
        if not isinstance(data, dict) or not isinstance(data.get("access_token"), str) or not data["access_token"]:
            raise DomainError("invalid_auth")
        now = time.time()
        try:
            for duration, expiry in (("expires_in", "expires_at"), ("refresh_token_expires_in", "refresh_expires_at")):
                if duration in data:
                    seconds = float(data[duration])
                    if not 0 < seconds <= 366 * 86400:
                        raise ValueError
                    data[expiry] = now + seconds
        except (ValueError, TypeError):
            raise DomainError("invalid_auth") from None
        return data

    async def exchange_code(self, code, verifier):
        return await self._token({"code": code, "code_verifier": verifier, "redirect_uri": self.settings.callback})

    async def refresh_token(self, token):
        return await self._token({"grant_type": "refresh_token", "refresh_token": token})

    async def user(self, token):
        return validate_user(await self._request("GET", "/user", token=token))

    async def _pages(self, path, token, key=None):
        result = []
        # shortcut: at most 2,000 entries per listing, add cursor UI when larger accounts are needed.
        for page in range(1, 21):
            data = await self._request("GET", path, token=token, params={"per_page": 100, "page": page})
            rows = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise DomainError("not_ready")
            result.extend(rows)
            if len(rows) < 100:
                return result
        raise DomainError("not_ready")

    async def installations(self, token):
        rows = await self._pages("/user/installations", token, "installations")
        return [{"id": row["id"], "account": row.get("account", {}).get("login"),
                 "suspended": bool(row.get("suspended_at"))} for row in rows]

    async def repositories(self, token):
        result = {}
        for installation in await self.installations(token):
            if installation["suspended"]:
                continue
            rows = await self._pages(f"/user/installations/{installation['id']}/repositories", token, "repositories")
            for row in rows:
                result[row["id"]] = {key: row.get(key) for key in ("id", "name", "full_name", "private", "default_branch", "description")}
                result[row["id"]]["installation_id"] = installation["id"]
        return list(result.values())

    async def repository(self, token, repository_id):
        for row in await self.repositories(token):
            if row["id"] == repository_id:
                return row
        raise DomainError("not_found")

    async def branches(self, token, repository_id):
        await self.repository(token, repository_id)
        rows = await self._pages(f"/repositories/{repository_id}/branches", token)
        return [{"name": row["name"], "sha": row["commit"]["sha"]} for row in rows]

    async def head(self, token, repository_id, branch):
        await self.repository(token, repository_id)
        data = await self._request("GET", f"/repositories/{repository_id}/commits/{quote(branch, safe='')}", token=token)
        sha = data.get("sha") if isinstance(data, dict) else None
        if not valid_sha(sha):
            raise DomainError("not_ready")
        return sha

    async def tree(self, token, repository_id, commit_sha):
        if not valid_sha(commit_sha):
            raise DomainError("invalid_request")
        data = await self._request("GET", f"/repositories/{repository_id}/git/trees/{commit_sha}", token=token, params={"recursive": "1"})
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list) or type(data.get("truncated")) is not bool:
            raise DomainError("not_ready")
        return data

    async def files(self, token, repository_id, commit_sha, paths):
        if not valid_sha(commit_sha) or len(paths) > 100 or any(not metadata_path(path) for path in paths):
            raise DomainError("invalid_request")
        result = {}
        for path in paths:
            data = await self._request("GET", f"/repositories/{repository_id}/contents/{quote(path, safe='/')}",
                token=token, params={"ref": commit_sha})
            if not isinstance(data, dict) or data.get("type") != "file" or data.get("encoding") != "base64" or type(data.get("size")) is not int or not 0 <= data["size"] <= 2 * 1024 * 1024 or not isinstance(data.get("content"), str):
                raise DomainError("not_ready")
            try:
                encoded = "".join(data["content"].split())
                if len(encoded) > 4 * ((data["size"] + 2) // 3):
                    raise ValueError
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError, KeyError):
                raise DomainError("not_ready") from None
            if len(content) != data["size"]:
                raise DomainError("not_ready")
            result[path] = content
        return result
