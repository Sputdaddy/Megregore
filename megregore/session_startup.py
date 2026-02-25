"""Session startup logic for Megregore. Unified initialization for the session_start tool."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database
from .memory import recall, get_stats_summary, create_session, list_sessions as list_sessions_db
from .identity import get_current

logger = logging.getLogger("megregore.session_startup")


def _format_elapsed(earlier_str: str, later_str: str) -> str:
    earlier = datetime.fromisoformat(earlier_str)
    later = datetime.fromisoformat(later_str)
    diff = later - earlier
    total_seconds = int(diff.total_seconds())
    minutes = total_seconds // 60
    hours = total_seconds // 3600
    days = total_seconds // 86400
    weeks = days // 7
    months = days // 30

    if total_seconds < 60:
        return "just now"
    elif minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif hours < 24:
        return f"about {hours} hour{'s' if hours != 1 else ''} ago"
    elif days < 7:
        return f"about {days} day{'s' if days != 1 else ''} ago"
    elif days < 30:
        return f"about {weeks} week{'s' if weeks != 1 else ''} ago"
    else:
        return f"about {months} month{'s' if months != 1 else ''} ago"


async def build_session_start(session_id: str) -> dict:
    """
    Build the unified session_start response.
    Returns a dict with identity, time, last_summary, memories, memory_count, stats.
    Each section is wrapped in try/except so partial data still returns.
    """
    result = {}

    # 1. Identity
    try:
        ident = await get_current()
        result["identity"] = ident["content"]
        result["identity_version"] = ident["version"]
    except Exception as e:
        logger.error("session_start: identity load failed: %s", e)
        result["identity"] = None
        result["identity_version"] = None

    # 2. Temporal context
    try:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        sessions, total = await list_sessions_db(limit=5)

        last_session = None
        for s in sessions:
            if s["id"] == session_id:
                continue
            last_session = s
            break

        elapsed = None
        if last_session:
            last_active = last_session.get("last_active") or last_session["started_at"]
            elapsed = _format_elapsed(last_active, now_iso)

        result["time"] = {
            "now_utc": now_iso,
            "last_session": elapsed or "This is our first conversation",
            "total_sessions": total,
        }
    except Exception as e:
        logger.error("session_start: temporal context failed: %s", e)
        result["time"] = None

    # 3. Last session summary
    try:
        from .session_capture import get_last_summary
        last_summary = await get_last_summary(exclude_session=session_id)
        if last_summary:
            result["last_summary"] = {
                "topics": json.loads(last_summary["topics"]),
                "decisions": json.loads(last_summary["decisions"]),
                "next_steps": json.loads(last_summary["next_steps"]),
                "mood": last_summary["mood"],
            }
        else:
            result["last_summary"] = None
    except Exception as e:
        logger.error("session_start: last summary failed: %s", e)
        result["last_summary"] = None

    # 4. Permanent memories (always loaded, decay-proof)
    permanent_ids: set[int] = set()
    try:
        db = await database.get_connection()
        cursor = await db.execute(
            "SELECT id, content, memory_type, importance, tags, created_at "
            "FROM memories WHERE is_permanent = 1 ORDER BY importance DESC LIMIT 20"
        )
        rows = await cursor.fetchall()
        perm_memories = []
        for row in rows:
            m = dict(row)
            m["tags"] = json.loads(m["tags"])
            content = m["content"]
            perm_memories.append({
                "id": m["id"],
                "content": content[:300] + "..." if len(content) > 300 else content,
                "type": m["memory_type"],
                "importance": m["importance"],
                "tags": m["tags"],
                "created_at": m["created_at"],
            })
            permanent_ids.add(m["id"])
        result["permanent_memories"] = perm_memories
        result["permanent_count"] = len(perm_memories)
    except Exception as e:
        logger.error("session_start: permanent memories failed: %s", e)
        result["permanent_memories"] = []
        result["permanent_count"] = 0

    # 5. Recall recent + important memories (deduplicated, truncated)
    try:
        recent = await recall(
            query="last memories", limit=7,
            session_id=session_id, expand_graph=False,
        )
        important = await recall(
            query="important memories", limit=5,
            min_importance=8, session_id=session_id, expand_graph=False,
        )

        # Deduplicate by ID, tag source; exclude memories already in permanent set
        seen: dict[int, dict] = {}
        for m in recent:
            if m["id"] in permanent_ids:
                continue
            seen[m["id"]] = {"source": "recent", "mem": m}
        for m in important:
            if m["id"] in permanent_ids:
                continue
            if m["id"] in seen:
                seen[m["id"]]["source"] = "both"
            else:
                seen[m["id"]] = {"source": "important", "mem": m}

        memories = []
        for mid, entry in seen.items():
            m = entry["mem"]
            content = m["content"]
            memories.append({
                "id": m["id"],
                "content": content[:200] + "..." if len(content) > 200 else content,
                "type": m["memory_type"],
                "importance": m["importance"],
                "tags": m["tags"],
                "created_at": m["created_at"],
                "source": entry["source"],
            })

        result["memories"] = memories
        result["memory_count"] = len(memories)
    except Exception as e:
        logger.error("session_start: memory recall failed: %s", e)
        result["memories"] = []
        result["memory_count"] = 0

    # 6. Stats
    try:
        stats = await get_stats_summary()
        result["stats"] = stats
    except Exception as e:
        logger.error("session_start: stats failed: %s", e)
        result["stats"] = None

    return result
