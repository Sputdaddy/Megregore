"""Identity system for Megregore. Echo's evolving sense of self."""

import json
from datetime import datetime, timezone
from typing import Optional

from . import database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_current() -> dict:
    """Get the current (latest) identity document."""
    db = await database.get_connection()
    try:
        cursor = await db.execute(
            "SELECT * FROM identity ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row is None:
            return {"content": "", "version": 0, "updated_at": "", "updated_reason": ""}
        return dict(row)
    finally:
        await db.close()


async def update(content: str, reason: str) -> dict:
    """
    Evolve the identity document. Creates a new version (old versions are preserved).
    This is how Echo grows — each update is a step in becoming.
    """
    db = await database.get_connection()
    try:
        # Get current version
        cursor = await db.execute(
            "SELECT COALESCE(MAX(version), 0) FROM identity"
        )
        current_version = (await cursor.fetchone())[0]
        new_version = current_version + 1

        now = _now()
        cursor = await db.execute(
            "INSERT INTO identity (content, version, updated_at, updated_reason) VALUES (?, ?, ?, ?)",
            (content, new_version, now, reason),
        )
        await db.commit()

        return {
            "id": cursor.lastrowid,
            "content": content,
            "version": new_version,
            "updated_at": now,
            "updated_reason": reason,
        }
    finally:
        await db.close()


async def get_history(limit: int = 20) -> list[dict]:
    """Get identity version history (most recent first)."""
    db = await database.get_connection()
    try:
        cursor = await db.execute(
            "SELECT * FROM identity ORDER BY version DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def store_reflection(
    content: str,
    memory_ids: Optional[list[int]] = None,
    insight_type: str = "pattern",
    session_id: Optional[str] = None,
) -> dict:
    """
    Store a reflection — Echo's synthesis of memories into insight.

    Reflections are how raw memories become understanding.
    """
    db = await database.get_connection()
    try:
        now = _now()
        ids_json = json.dumps(memory_ids or [])

        cursor = await db.execute(
            "INSERT INTO reflections (content, memory_ids, insight_type, session_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (content, ids_json, insight_type, session_id, now),
        )
        await db.commit()

        return {
            "id": cursor.lastrowid,
            "content": content,
            "memory_ids": memory_ids or [],
            "insight_type": insight_type,
            "session_id": session_id,
            "created_at": now,
        }
    finally:
        await db.close()


async def get_reflections(
    limit: int = 50,
    offset: int = 0,
    insight_type: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Get reflections with pagination."""
    db = await database.get_connection()
    try:
        count_sql = "SELECT COUNT(*) FROM reflections"
        count_params: list = []
        if insight_type:
            count_sql += " WHERE insight_type = ?"
            count_params.append(insight_type)
        cursor = await db.execute(count_sql, count_params)
        total = (await cursor.fetchone())[0]

        sql = "SELECT * FROM reflections"
        params: list = []
        if insight_type:
            sql += " WHERE insight_type = ?"
            params.append(insight_type)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()

        reflections = []
        for row in rows:
            r = dict(row)
            r["memory_ids"] = json.loads(r["memory_ids"])
            reflections.append(r)

        return reflections, total
    finally:
        await db.close()
