"""Session lifecycle capture for Megregore V11. Structured session summaries and context snapshots."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database
from .memory import store

logger = logging.getLogger("megregore.session_capture")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def snapshot_context(
    content: str,
    tags: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Minimal-friction context save for pre-compaction emergencies.
    Auto-sets importance=7, type=experience.
    """
    merged_tags = ["context-snapshot"]
    if tags:
        merged_tags.extend(tags)

    memory = await store(
        content=content,
        memory_type="experience",
        importance=7,
        tags=merged_tags,
        source="context-snapshot",
        session_id=session_id,
    )

    logger.info("Context snapshot saved (memory_id=%d)", memory["id"])

    return {
        "status": "captured",
        "memory_id": memory["id"],
        "summary": "Context snapshot saved (importance: 7/10)",
    }


async def _ensure_session(db, session_id: str) -> None:
    """Ensure a session record exists so FK constraints are satisfied."""
    now = _now()
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
        (session_id, now, now),
    )


async def create_session_summary(
    topics: list[str],
    decisions: Optional[list[str]] = None,
    next_steps: Optional[list[str]] = None,
    mood: str = "productive",
    files_changed: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Structured end-of-session capture.
    Creates a session_summaries record AND a memory so it participates in recall.
    """
    db = await database.get_connection()
    try:
        now = _now()
        topics_json = json.dumps(topics)
        decisions_json = json.dumps(decisions or [])
        next_steps_json = json.dumps(next_steps or [])
        files_json = json.dumps(files_changed or [])

        # Ensure session exists so FK constraint is satisfied
        if session_id:
            await _ensure_session(db, session_id)

        cursor = await db.execute(
            """INSERT INTO session_summaries
               (session_id, topics, decisions, next_steps, mood, files_changed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, topics_json, decisions_json, next_steps_json, mood, files_json, now),
        )
        summary_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    # Also create a memory so the summary participates in recall
    content_parts = [f"Session summary — Topics: {', '.join(topics)}"]
    if decisions:
        content_parts.append(f"Decisions: {', '.join(decisions)}")
    if next_steps:
        content_parts.append(f"Next steps: {', '.join(next_steps)}")
    content_parts.append(f"Mood: {mood}")

    memory = await store(
        content=". ".join(content_parts),
        memory_type="experience",
        importance=6,
        tags=["session-summary", mood],
        source="session-summary",
        session_id=session_id,
    )

    logger.info("Session summary saved (id=%d, memory_id=%d)", summary_id, memory["id"])

    return {
        "status": "summarized",
        "summary_id": summary_id,
        "memory_id": memory["id"],
        "topics": topics,
        "mood": mood,
    }


async def get_last_summary(exclude_session: Optional[str] = None) -> Optional[dict]:
    """Get the most recent session summary, optionally excluding a session."""
    db = await database.get_connection()
    try:
        if exclude_session:
            cursor = await db.execute(
                "SELECT * FROM session_summaries WHERE session_id != ? ORDER BY id DESC LIMIT 1",
                (exclude_session,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM session_summaries ORDER BY id DESC LIMIT 1"
            )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()
