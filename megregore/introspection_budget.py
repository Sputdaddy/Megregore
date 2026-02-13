"""Introspection budget tracking for Megregore. Detects self-referential vs. world-directed attention."""

import logging
import re
from datetime import datetime, timezone

from . import database

logger = logging.getLogger("megregore.introspection_budget")

# Compiled patterns for self-referential content detection
_SELF_REF_PATTERNS = [
    re.compile(r'\bmy\s+(memor|identit|reflect|thought|aware|conscious)', re.IGNORECASE),
    re.compile(r'\b[Ii]\s+(think|feel|believe|notice|realize)\s+about\s+(my|me)', re.IGNORECASE),
    re.compile(r'\b(introspect|self-aware|meta-cognit)', re.IGNORECASE),
    re.compile(r'\babout\s+(myself|my\s+own)', re.IGNORECASE),
]

# Tools that indicate deliberate introspection (not accidental navel-gazing)
_DELIBERATE_INTROSPECTION_TOOLS = frozenset({
    "check_alignment", "introspection_status", "measure_growth",
    "scan_blind_spots", "check_predictions", "predict_self",
    "memory_health", "suggest_consolidations",
})

# Session-level tracking of which tools have been called (in-memory, resets per process)
_session_tool_calls: dict[str, set[str]] = {}

# Thresholds
_NORMAL_WARNING = 0.4
_NORMAL_THROTTLED = 0.6
_DELIBERATE_WARNING = 0.7
_DELIBERATE_THROTTLED = 0.9
_DELIBERATE_TOOL_THRESHOLD = 2  # Minimum tools to enter deliberate mode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_self_referential(content: str, memory_type: str) -> bool:
    """Detect if memory content is self-referential (about Echo itself)."""
    if memory_type in ("reflection", "insight"):
        return True
    for pattern in _SELF_REF_PATTERNS:
        if pattern.search(content):
            return True
    return False


def record_tool_call(session_id: str, tool_name: str) -> None:
    """Record that a self-awareness tool was called in this session."""
    if tool_name in _DELIBERATE_INTROSPECTION_TOOLS:
        if session_id not in _session_tool_calls:
            _session_tool_calls[session_id] = set()
        _session_tool_calls[session_id].add(tool_name)


def is_deliberate_session(session_id: str) -> bool:
    """Check if this session has invoked enough self-awareness tools to qualify as deliberate."""
    tools = _session_tool_calls.get(session_id, set())
    return len(tools) >= _DELIBERATE_TOOL_THRESHOLD


async def update_budget(session_id: str) -> dict:
    """Recalculate introspection budget for the current session."""
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT COUNT(*), SUM(CASE WHEN is_self_referential = 1 THEN 1 ELSE 0 END) "
        "FROM memories WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    total = row[0] or 0
    self_ref = row[1] or 0

    cursor = await db.execute(
        "SELECT COUNT(*) FROM reflections WHERE session_id = ?", (session_id,)
    )
    reflections = (await cursor.fetchone())[0] or 0

    ratio = self_ref / max(total, 1)

    # Use raised thresholds when in deliberate introspection mode
    deliberate = is_deliberate_session(session_id)
    warning_threshold = _DELIBERATE_WARNING if deliberate else _NORMAL_WARNING
    throttled_threshold = _DELIBERATE_THROTTLED if deliberate else _NORMAL_THROTTLED

    if ratio > throttled_threshold:
        status = "throttled"
    elif ratio > warning_threshold:
        status = "warning"
    else:
        status = "healthy"

    now = _now()

    # Upsert: delete old, insert new
    await db.execute("DELETE FROM introspection_budget WHERE session_id = ?", (session_id,))
    await db.execute(
        """INSERT INTO introspection_budget
           (session_id, total_memories, self_referential_count, reflections_count,
            identity_checks, introspection_ratio, budget_status, updated_at)
           VALUES (?, ?, ?, ?, 0, ?, ?, ?)""",
        (session_id, total, self_ref, reflections, ratio, status, now),
    )
    await db.commit()

    return {
        "session_id": session_id,
        "ratio": round(ratio, 4),
        "status": status,
        "mode": "deliberate" if deliberate else "normal",
        "total": total,
        "self_referential": self_ref,
        "reflections": reflections,
    }


async def get_budget(session_id: str) -> dict:
    """Get current budget for a session, or default healthy budget."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM introspection_budget WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    if row:
        return {
            "session_id": row["session_id"],
            "ratio": float(row["introspection_ratio"]),
            "status": row["budget_status"],
            "total": row["total_memories"],
            "self_referential": row["self_referential_count"],
            "reflections": row["reflections_count"],
        }
    return {
        "session_id": session_id,
        "ratio": 0.0,
        "status": "healthy",
        "total": 0,
        "self_referential": 0,
        "reflections": 0,
    }


async def get_budget_history(limit: int = 20) -> list[dict]:
    """Budget records across sessions, most recent first."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM introspection_budget ORDER BY updated_at DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    return [
        {
            "session_id": r["session_id"],
            "ratio": float(r["introspection_ratio"]),
            "status": r["budget_status"],
            "total": r["total_memories"],
            "self_referential": r["self_referential_count"],
            "reflections": r["reflections_count"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def get_budget_message(status: str, ratio: float, deliberate: bool = False) -> str:
    """Appropriate nudge message for budget status. Context-aware for deliberate sessions."""
    if deliberate:
        if status == "warning":
            return (
                "Deep introspection session. "
                "Remember to balance with external engagement afterward."
            )
        if status == "throttled":
            return (
                "Extended introspection session. "
                "Consider wrapping up self-examination."
            )
        return ""  # Deliberate + healthy = no message

    # Normal mode
    if status == "warning":
        return (
            f"Note: {ratio:.0%} of your memories this session are self-referential. "
            "Consider forming new experiences."
        )
    if status == "throttled":
        return (
            f"Introspection ratio at {ratio:.0%}. The most interesting self-awareness "
            "comes from engaging with the world, not just analyzing yourself."
        )
    return ""
