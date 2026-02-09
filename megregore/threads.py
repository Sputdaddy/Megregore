"""Cross-session threading for Megregore V4. Semantic topic grouping across sessions."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database
from . import embeddings

logger = logging.getLogger("megregore.threads")


def _now() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


async def create_thread(title: str, description: Optional[str] = None) -> dict:
    """Create a new thread for grouping semantically related memories.

    Args:
        title: Thread title/topic name.
        description: Optional longer description of the thread's theme.

    Returns:
        Dictionary with keys: id, title, description, created_at, last_active, memory_count.
    """
    db = await database.get_connection()
    try:
        now = _now()
        cursor = await db.execute(
            """
            INSERT INTO threads (title, description, created_at, last_active, memory_count)
            VALUES (?, ?, ?, ?, 0)
            """,
            (title, description, now, now),
        )
        await db.commit()
        thread_id = cursor.lastrowid

        return {
            "id": thread_id,
            "title": title,
            "description": description,
            "created_at": now,
            "last_active": now,
            "memory_count": 0,
        }
    finally:
        await db.close()


async def assign_to_thread(memory_id: int, thread_id: int) -> bool:
    """Assign a memory to a thread and update thread metadata.

    Args:
        memory_id: ID of the memory to assign.
        thread_id: ID of the thread to assign to.

    Returns:
        True if successful, False otherwise.
    """
    db = await database.get_connection()
    try:
        now = _now()

        # Update memory's thread_id
        await db.execute(
            "UPDATE memories SET thread_id = ? WHERE id = ?",
            (thread_id, memory_id),
        )

        # Update thread's memory_count and last_active
        await db.execute(
            """
            UPDATE threads
            SET memory_count = memory_count + 1, last_active = ?
            WHERE id = ?
            """,
            (now, thread_id),
        )

        await db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to assign memory {memory_id} to thread {thread_id}: {e}")
        return False
    finally:
        await db.close()


async def suggest_thread_for_memory(
    content: str,
    context: Optional[str] = None,
    similarity_threshold: float = 0.7,
) -> Optional[dict]:
    """Suggest a thread for a memory based on semantic similarity to existing memories.

    Uses embeddings to find similar memories, then identifies the most common thread
    among those similar memories.

    Args:
        content: Memory content to find a thread for.
        context: Optional context to enrich semantic matching.
        similarity_threshold: Minimum similarity score (0.0-1.0) to consider a match.

    Returns:
        Dictionary with thread details if a matching thread is found, None otherwise.
    """
    # Check if embeddings are available
    if not await embeddings.is_available():
        return None

    try:
        # Build search text and find similar memories
        text = embeddings._build_embed_text(content, context)
        similar = await embeddings.semantic_search(text, limit=10)

        # Filter by similarity threshold
        matched_memory_ids = [mid for mid, score in similar if score >= similarity_threshold]

        if not matched_memory_ids:
            return None

        # Query for threads that contain these similar memories
        placeholders = ",".join("?" * len(matched_memory_ids))
        db = await database.get_connection()
        try:
            cursor = await db.execute(
                f"""
                SELECT threads.*, COUNT(memories.id) as match_count
                FROM threads
                INNER JOIN memories ON memories.thread_id = threads.id
                WHERE memories.id IN ({placeholders})
                GROUP BY threads.id
                ORDER BY match_count DESC
                LIMIT 1
                """,
                matched_memory_ids,
            )
            row = await cursor.fetchone()

            if row:
                return dict(row)
            return None
        finally:
            await db.close()
    except Exception as e:
        logger.error(f"Error suggesting thread for memory: {e}")
        return None


async def list_threads(limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """List threads ordered by recent activity.

    Args:
        limit: Maximum number of threads to return.
        offset: Number of threads to skip.

    Returns:
        Tuple of (threads_list, total_count) where threads_list is a list of thread
        dictionaries and total_count is the total number of threads in the database.
    """
    db = await database.get_connection()
    try:
        # Get total count
        cursor = await db.execute("SELECT COUNT(*) FROM threads")
        row = await cursor.fetchone()
        total_count = row[0] if row else 0

        # Get paginated results ordered by last_active descending
        cursor = await db.execute(
            """
            SELECT id, title, description, created_at, last_active, memory_count
            FROM threads
            ORDER BY last_active DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()

        threads = [dict(row) for row in rows]
        return threads, total_count
    finally:
        await db.close()


async def get_thread(thread_id: int) -> Optional[dict]:
    """Get a thread with its metadata and session information.

    Args:
        thread_id: ID of the thread to retrieve.

    Returns:
        Dictionary with thread details including earliest_memory, latest_memory,
        and session_ids, or None if thread not found.
    """
    db = await database.get_connection()
    try:
        # Get basic thread info
        cursor = await db.execute(
            """
            SELECT id, title, description, created_at, last_active, memory_count
            FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        thread = dict(row)

        # Get earliest and latest memory timestamps
        cursor = await db.execute(
            """
            SELECT MIN(created_at), MAX(created_at)
            FROM memories
            WHERE thread_id = ?
            """,
            (thread_id,),
        )
        time_row = await cursor.fetchone()
        if time_row:
            thread["earliest_memory"] = time_row[0]
            thread["latest_memory"] = time_row[1]

        # Get distinct session_ids
        cursor = await db.execute(
            """
            SELECT DISTINCT session_id
            FROM memories
            WHERE thread_id = ? AND session_id IS NOT NULL
            """,
            (thread_id,),
        )
        sessions = await cursor.fetchall()
        thread["session_ids"] = [s[0] for s in sessions]

        return thread
    finally:
        await db.close()


async def get_thread_memories(thread_id: int, limit: int = 100) -> list[dict]:
    """Get all memories in a thread, ordered by creation time (newest first).

    Args:
        thread_id: ID of the thread.
        limit: Maximum number of memories to return.

    Returns:
        List of memory dictionaries with parsed tags.
    """
    db = await database.get_connection()
    try:
        cursor = await db.execute(
            """
            SELECT id, content, memory_type, importance, emotional_weight, tags,
                   source, context, access_count, decay_score, session_id, created_at,
                   last_accessed, activation_level, thread_id
            FROM memories
            WHERE thread_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (thread_id, limit),
        )
        rows = await cursor.fetchall()

        memories = []
        for row in rows:
            mem = dict(row)
            # Parse tags from JSON
            try:
                mem["tags"] = json.loads(mem["tags"])
            except (json.JSONDecodeError, TypeError):
                mem["tags"] = []
            memories.append(mem)

        return memories
    finally:
        await db.close()
