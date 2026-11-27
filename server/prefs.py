"""Per-player preferences such as first-time tutorial completion.

The player_prefs table is additive (CREATE TABLE IF NOT EXISTS). It is applied
automatically on local SQLite and in tests. It is NOT applied when a hosted
DATABASE_URL is set, unless ALLOW_SCHEMA_MIGRATE=1. See
docs/migrations/2026-11-28-player-prefs.md. Do not point this branch at the
production Postgres database.
"""

from __future__ import annotations

import json
import os
from typing import Any

def schema_migrate_allowed() -> bool:
    if (os.environ.get("ALLOW_SCHEMA_MIGRATE") or "").strip() == "1":
        return True
    if (os.environ.get("DATABASE_URL") or "").strip():
        return False
    return True


def ensure_schema(conn: Any) -> None:
    if not schema_migrate_allowed():
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS player_prefs (
            player_id TEXT PRIMARY KEY,
            tutorial TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (player_id) REFERENCES players(id)
        );
        """
    )


def get_tutorial(conn: Any, player_id: str) -> dict[str, Any]:
    try:
        row = conn.execute(
            "SELECT tutorial FROM player_prefs WHERE player_id = ?",
            (player_id,),
        ).fetchone()
    except Exception:
        return {"status": "pending"}
    if not row or not row["tutorial"]:
        return {"status": "pending"}
    try:
        data = json.loads(row["tutorial"])
        return data if isinstance(data, dict) else {"status": "pending"}
    except Exception:
        return {"status": "pending"}


def set_tutorial(conn: Any, player_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if not schema_migrate_allowed():
        # Do not write a table that was never migrated on this database.
        return {"status": "pending", "stored": False}
    status = str(state.get("status") or "pending")
    if status not in ("pending", "done", "skipped"):
        status = "pending"
    slots = bool(state.get("slots"))
    table = bool(state.get("table"))
    if status in ("done", "skipped"):
        slots = table = True
    payload = {"status": status, "slots": slots, "table": table}
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    raw = json.dumps(payload)
    conn.execute(
        """
        INSERT INTO player_prefs (player_id, tutorial, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (player_id) DO UPDATE SET tutorial = excluded.tutorial, updated_at = excluded.updated_at
        """,
        (player_id, raw, now),
    )
    return payload
