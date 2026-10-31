"""GitHub App web-flow configuration; no installation private key is needed."""
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import dotenv_values
from docweave.core.paths import ROOT


@dataclass(frozen=True)
class GitHubSettings:
    origin: str
    client_id: str
    client_secret: str = field(repr=False)
    encryption_key: str = field(repr=False)
    secure: bool
    issuer: str = "https://github.com"
    app_slug: str | None = None

    @property
    def callback(self):
        return self.origin + "/api/v1/auth/callback"

    @property
    def installation_url(self):
        return f"https://github.com/apps/{self.app_slug}/installations/new" if self.app_slug else None

    @classmethod
    def load(cls, values=None):
        if values is None:
            values = {**dotenv_values(ROOT / ".env"), **os.environ}
        required = ("APP_ORIGIN", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "AUTH_ENCRYPTION_KEY")
        if not any(values.get(key) for key in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET")):
            return None
        try:
            if not all(isinstance(values.get(key), str) and values[key].strip() for key in required):
                raise ValueError
            if values.get("AUTH_LOCALHOST_HTTP", "false") not in ("true", "false"):
                raise ValueError
            local = values.get("AUTH_LOCALHOST_HTTP") == "true"
            origin = urlsplit(values["APP_ORIGIN"])
            if not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ("", "/"):
                raise ValueError
            if local and origin.hostname not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError
            if origin.scheme != "https" and not (local and origin.scheme == "http"):
                raise ValueError
            host = f"[{origin.hostname}]" if ":" in origin.hostname else origin.hostname
            port = origin.port
            authority = host if port is None or port == {"http": 80, "https": 443}[origin.scheme] else f"{host}:{port}"
            Fernet(values["AUTH_ENCRYPTION_KEY"].encode())
            slug = values.get("GITHUB_APP_SLUG") or None
            if slug is not None and (not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?", slug)):
                raise ValueError
            return cls(f"{origin.scheme}://{authority}", values["GITHUB_CLIENT_ID"],
                       values["GITHUB_CLIENT_SECRET"], values["AUTH_ENCRYPTION_KEY"], not local, app_slug=slug)
        except (ValueError, TypeError):
            raise ValueError("GitHub login requires complete App configuration, a Fernet key, and HTTPS or explicit loopback HTTP.") from None
