import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from docweave.core.paths import ROOT
from sqlalchemy import make_url
from sqlalchemy.engine import URL
from sqlalchemy.exc import ArgumentError


@dataclass(frozen=True)
class AuthSettings:
    origin: str
    issuer: str
    client_id: str
    client_secret: str = field(repr=False)
    encryption_key: str = field(repr=False)
    secure: bool
    google_enabled: bool = False
    github_enabled: bool = False

    @property
    def callback(self):
        return self.origin + "/api/v1/auth/callback"

    @classmethod
    def load(cls, values=None):
        if values is None:
            values = {**dotenv_values(ROOT / ".env"), **os.environ}
        required = ("APP_ORIGIN", "OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "AUTH_ENCRYPTION_KEY")
        if not any(values.get(key) for key in required):
            return None
        try:
            if not all(isinstance(values.get(key), str) and values[key].strip() for key in required):
                raise ValueError
            for key in ("AUTH_LOCALHOST_HTTP", "OIDC_GOOGLE_ENABLED", "OIDC_GITHUB_ENABLED"):
                if values.get(key, "false") not in ("true", "false"):
                    raise ValueError
            local = values.get("AUTH_LOCALHOST_HTTP") == "true"
            for key in ("APP_ORIGIN", "OIDC_ISSUER"):
                url = urlsplit(values[key])
                if not url.hostname or url.username or url.password or url.query or url.fragment:
                    raise ValueError
                if local and url.hostname not in ("localhost", "127.0.0.1", "::1"):
                    raise ValueError
                if url.scheme != "https" and not (local and url.scheme == "http"):
                    raise ValueError
                if key == "APP_ORIGIN" and url.path not in ("", "/"):
                    raise ValueError
                url.port  # Reject malformed ports without exposing configuration.
            origin = urlsplit(values["APP_ORIGIN"])
            host = f"[{origin.hostname}]" if ":" in origin.hostname else origin.hostname
            port = origin.port
            authority = host if port is None or port == {"http": 80, "https": 443}[origin.scheme] else f"{host}:{port}"
            Fernet(values["AUTH_ENCRYPTION_KEY"].encode())
            return cls(f"{origin.scheme}://{authority}", values["OIDC_ISSUER"].rstrip("/"), values["OIDC_CLIENT_ID"],
                values["OIDC_CLIENT_SECRET"], values["AUTH_ENCRYPTION_KEY"], not local,
                values.get("OIDC_GOOGLE_ENABLED") == "true", values.get("OIDC_GITHUB_ENABLED") == "true")
        except (ValueError, TypeError):
            raise ValueError("Auth requires complete OIDC configuration, a Fernet key, and HTTPS or explicit loopback HTTP.") from None

def database_url(name: str) -> URL:
    value = os.environ.get(name)
    if value is None:
        value = dotenv_values(ROOT / ".env").get(name)
    if not value:
        raise ValueError(f"{name} must be set")
    try:
        url = make_url(value)
        if url.drivername != "postgresql+asyncpg" or not all((url.host, url.database, url.username, url.password)):
            raise ValueError
    except (ArgumentError, ValueError):
        raise ValueError(f"{name} must be a complete postgresql+asyncpg connection URL") from None
    return url

def storage_root():
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    return Path(values.get("INGESTION_STORAGE_ROOT") or ROOT / "storage").resolve()
