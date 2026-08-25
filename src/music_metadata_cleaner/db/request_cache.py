"""SQLite request cache for provider payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any


class RequestCache:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, provider: str, cache_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT payload_json FROM request_cache WHERE provider = ? AND cache_key = ?",
            (provider, cache_key),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def set(self, provider: str, cache_key: str, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO request_cache(cache_key, provider, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    provider = excluded.provider,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (cache_key, provider, json.dumps(payload, ensure_ascii=False), now),
            )

