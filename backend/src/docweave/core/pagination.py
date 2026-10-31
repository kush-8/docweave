"""Encrypted keyset cursors bind navigation to an actor and a concrete resource list."""

import json
from datetime import datetime
from uuid import UUID
from cryptography.fernet import Fernet, InvalidToken
from docweave.core.errors import DomainError


def decode_cursor(settings, cursor, actor_id, resource):
    if cursor is None:
        return None, None
    try:
        saved = json.loads(Fernet(settings.encryption_key).decrypt(cursor.encode()))
        if saved["actor"] != str(actor_id) or saved["resource"] != resource:
            raise ValueError
        after = datetime.fromisoformat(saved["created_at"])
        if after.tzinfo is None or not isinstance(saved["id"], str):
            raise ValueError
        return after, UUID(saved["id"])
    except (InvalidToken, ValueError, TypeError, KeyError):
        raise DomainError("invalid_cursor") from None


def page(settings, rows, limit, actor_id, resource):
    items, cursor = rows[:limit], None
    if len(rows) > limit:
        last = items[-1]
        cursor = Fernet(settings.encryption_key).encrypt(json.dumps({"actor": str(actor_id), "resource": resource,
            "id": str(last["id"]), "created_at": last["created_at"].isoformat()}).encode()).decode()
    return {"items": items, "next_cursor": cursor}
