"""Proactive memory surfacing for Megregore V4. Surface relevant memories without explicit search."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database
from . import embeddings

logger = logging.getLogger("megregore.surfacing")


def _now() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


async def surface_relevant(
    context: str,
    limit: int = 10,
    session_id: Optional[str] = None,
) -> list[dict]:
    """
    Surface relevant memories based on context without explicit search.

    Algorithm:
    1. Semantic search for candidates using context
    2. Exclude memories already accessed this session
    3. Score by: similarity * 0.40 + activation * 0.30 + importance * 0.20 + has_been_used * 0.10
    4. Return top N results

    Args:
        context: What's being discussed or thought about.
        limit: Max memories to surface (default 10).
        session_id: Current session ID; exclude already-accessed memories.

    Returns:
        List of memory dicts with _surfacing_score and _similarity metadata.
    """
    if not await embeddings.is_available():
        return []

    # Step 1: Get semantic matches (overquery for filtering headroom)
    similar = await embeddings.semantic_search(context, limit=limit * 3)
    if not similar:
        return []

    similarity_map = {mid: score for mid, score in similar}
    candidate_ids = list(similarity_map.keys())

    db = await database.get_connection()
    try:
        # Step 2: Find memories already accessed this session
        excluded_ids = set()
        if session_id:
            cursor = await db.execute(
                "SELECT DISTINCT memory_id FROM memory_access_log WHERE session_id = ?",
                (session_id,),
            )
            excluded_ids = {row[0] for row in await cursor.fetchall()}

        # Step 3: Fetch candidate memory rows
        placeholders = ",".join("?" * len(candidate_ids))
        cursor = await db.execute(
            f"SELECT * FROM memories WHERE id IN ({placeholders})",
            candidate_ids,
        )
        rows = await cursor.fetchall()

        # Step 4: Score and filter
        candidates = []
        for row in rows:
            mem = dict(row)

            # Skip if already accessed this session
            if mem["id"] in excluded_ids:
                continue

            mem["tags"] = json.loads(mem["tags"])

            similarity = similarity_map.get(mem["id"], 0.0)
            activation = mem.get("activation_level") or 1.0
            importance = mem["importance"] / 10.0
            has_been_used = 1.0 if mem["access_count"] > 0 else 0.0

            surfacing_score = (
                similarity * 0.40
                + activation * 0.30
                + importance * 0.20
                + has_been_used * 0.10
            )

            mem["_surfacing_score"] = round(surfacing_score, 4)
            mem["_similarity"] = round(similarity, 4)
            candidates.append(mem)

        # Step 5: Sort and limit
        candidates.sort(key=lambda m: m["_surfacing_score"], reverse=True)
        results = candidates[:limit]

        # Step 6: Log surfacing events (fire-and-forget)
        if session_id and results:
            now = _now()
            try:
                for mem in results:
                    await db.execute(
                        """INSERT INTO memory_access_log
                           (memory_id, access_type, session_id, accessed_at)
                           VALUES (?, ?, ?, ?)""",
                        (mem["id"], "surfaced", session_id, now),
                    )
                await db.commit()
            except Exception:
                pass

        return results
    finally:
        await db.close()
