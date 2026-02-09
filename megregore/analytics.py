"""Memory usage analytics for Megregore V4. Access logging and insights."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import database

logger = logging.getLogger("megregore.analytics")


def _now() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


async def log_access(
    memory_id: int,
    access_type: str,
    session_id: Optional[str] = None,
    context_json: Optional[dict] = None,
) -> None:
    """
    Log a memory access event for analytics.

    Fire-and-forget: silently fails if database unavailable, never blocks calling code.

    Args:
        memory_id: ID of the accessed memory
        access_type: One of "recall", "get", "graph_expansion", "surfaced"
        session_id: Optional session ID for grouping accesses
        context_json: Optional context dict (will be JSON-serialized)
    """
    try:
        db = await database.get_connection()
        context_str = json.dumps(context_json) if context_json else None

        await db.execute(
            """
            INSERT INTO memory_access_log (memory_id, access_type, context_json, session_id, accessed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (memory_id, access_type, context_str, session_id, _now()),
        )
        await db.commit()
    except Exception as e:
        # Silently fail — never block calling code
        logger.error(f"Failed to log access for memory {memory_id}: {e}")


async def get_top_accessed(days: int = 30, limit: int = 20) -> list[dict]:
    """
    Get memories with the most accesses in the last N days.

    Args:
        days: Look back this many days (default 30)
        limit: Maximum number of results (default 20)

    Returns:
        List of dicts with keys:
            - id: memory ID
            - content: truncated to 200 characters
            - importance: importance level
            - activation_level: activation level
            - recent_access_count: number of accesses in the time window
    """
    db = await database.get_connection()
    try:
        # Calculate cutoff timestamp
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        rows = await db.execute(
            """
            SELECT
                m.id,
                m.content,
                m.importance,
                m.activation_level,
                COUNT(aal.id) as recent_access_count
            FROM memories m
            LEFT JOIN memory_access_log aal ON m.id = aal.memory_id AND aal.accessed_at >= ?
            GROUP BY m.id
            HAVING recent_access_count > 0
            ORDER BY recent_access_count DESC
            LIMIT ?
            """,
            (cutoff, limit),
        )

        result = []
        async for row in rows:
            content = row["content"]
            if len(content) > 200:
                content = content[:197] + "..."

            result.append(
                {
                    "id": row["id"],
                    "content": content,
                    "importance": row["importance"],
                    "activation_level": row["activation_level"],
                    "recent_access_count": row["recent_access_count"],
                }
            )

        return result

    finally:
        await db.close()


async def get_orphan_memories(min_age_days: int = 7, limit: int = 20) -> list[dict]:
    """
    Find memories that have never been accessed and are older than min_age_days.

    Args:
        min_age_days: Minimum age in days (default 7)
        limit: Maximum number of results (default 20)

    Returns:
        List of memory dicts with keys:
            - id: memory ID
            - content: full content
            - importance: importance level
            - tags: parsed JSON array of tags
            - created_at: creation timestamp
            - memory_type: type of memory
    """
    db = await database.get_connection()
    try:
        # Calculate cutoff timestamp for age
        cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).isoformat()

        rows = await db.execute(
            """
            SELECT
                m.id,
                m.content,
                m.importance,
                m.tags,
                m.created_at,
                m.memory_type
            FROM memories m
            LEFT JOIN memory_access_log aal ON m.id = aal.memory_id
            WHERE aal.id IS NULL
            AND m.created_at < ?
            ORDER BY m.created_at ASC
            LIMIT ?
            """,
            (cutoff, limit),
        )

        result = []
        async for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "importance": row["importance"],
                    "tags": json.loads(row["tags"]),
                    "created_at": row["created_at"],
                    "memory_type": row["memory_type"],
                }
            )

        return result

    finally:
        await db.close()


async def get_access_timeline(memory_id: int) -> dict:
    """
    Get access history for a single memory, grouped by access type.

    Args:
        memory_id: ID of the memory to inspect

    Returns:
        Dict with keys:
            - memory_id: the queried memory ID
            - total_accesses: total number of accesses
            - by_type: list of dicts with access_type, count, and most_recent timestamp
    """
    db = await database.get_connection()
    try:
        # Get total count and breakdown by type
        rows = await db.execute(
            """
            SELECT
                access_type,
                COUNT(*) as count,
                MAX(accessed_at) as most_recent
            FROM memory_access_log
            WHERE memory_id = ?
            GROUP BY access_type
            ORDER BY count DESC
            """,
            (memory_id,),
        )

        by_type = []
        total_accesses = 0

        async for row in rows:
            by_type.append(
                {
                    "access_type": row["access_type"],
                    "count": row["count"],
                    "most_recent": row["most_recent"],
                }
            )
            total_accesses += row["count"]

        return {
            "memory_id": memory_id,
            "total_accesses": total_accesses,
            "by_type": by_type,
        }

    finally:
        await db.close()


async def compute_analytics() -> dict:
    """
    Compute aggregate analytics snapshot.

    Returns:
        Dict with keys:
            - total_memories: count of all memories
            - total_accesses: count of all access log entries
            - avg_activation: average activation_level (rounded to 3 decimals)
            - orphan_count: memories with no accesses
            - threaded_count: memories with thread_id set
            - thread_coverage_pct: (threaded_count / total_memories) * 100 (3 decimals)
            - access_by_type: dict mapping access_type -> count
    """
    db = await database.get_connection()
    try:
        # Total memories
        total_mem_row = await db.execute("SELECT COUNT(*) as cnt FROM memories")
        total_mem = (await total_mem_row.fetchone())["cnt"]

        # Total accesses
        total_acc_row = await db.execute(
            "SELECT COUNT(*) as cnt FROM memory_access_log"
        )
        total_acc = (await total_acc_row.fetchone())["cnt"]

        # Average activation level
        avg_act_row = await db.execute(
            "SELECT AVG(activation_level) as avg FROM memories"
        )
        avg_act_val = (await avg_act_row.fetchone())["avg"]
        avg_act = round(avg_act_val if avg_act_val is not None else 0.0, 3)

        # Orphan count (no accesses)
        orphan_row = await db.execute(
            """
            SELECT COUNT(*) as cnt FROM memories m
            LEFT JOIN memory_access_log aal ON m.id = aal.memory_id
            WHERE aal.id IS NULL
            """
        )
        orphan_cnt = (await orphan_row.fetchone())["cnt"]

        # Threaded count
        thread_row = await db.execute(
            "SELECT COUNT(*) as cnt FROM memories WHERE thread_id IS NOT NULL"
        )
        thread_cnt = (await thread_row.fetchone())["cnt"]

        # Thread coverage percentage
        thread_cov = (
            round((thread_cnt / total_mem) * 100, 3) if total_mem > 0 else 0.0
        )

        # Access breakdown by type
        access_type_rows = await db.execute(
            """
            SELECT access_type, COUNT(*) as cnt
            FROM memory_access_log
            GROUP BY access_type
            ORDER BY cnt DESC
            """
        )

        access_by_type = {}
        async for row in access_type_rows:
            access_by_type[row["access_type"]] = row["cnt"]

        return {
            "total_memories": total_mem,
            "total_accesses": total_acc,
            "avg_activation": avg_act,
            "orphan_count": orphan_cnt,
            "threaded_count": thread_cnt,
            "thread_coverage_pct": thread_cov,
            "access_by_type": access_by_type,
        }

    finally:
        await db.close()
