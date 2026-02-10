"""Auto-link inference for Megregore V4. Automatic semantic relationship detection."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database
from . import embeddings

logger = logging.getLogger("megregore.auto_linker")


def _now() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


async def _find_unlinked_pairs(threshold: float = 0.80) -> list[tuple[int, int, float]]:
    """Find high-similarity memory pairs without existing links.

    Algorithm:
    1. Fetch all memories from database
    2. Build set of existing link pairs (normalized to min,max ordering)
    3. For each memory, search for top-10 semantic neighbors
    4. Filter: similarity >= threshold, no existing link, not self
    5. Deduplicate pairs (keep highest similarity)
    6. Sort by similarity descending

    Args:
        threshold: Minimum similarity score (0.0-1.0) to consider.

    Returns:
        List of (id_a, id_b, similarity) tuples sorted by similarity descending.
    """
    if not await embeddings.is_available():
        logger.warning("Embeddings unavailable, cannot find unlinked pairs")
        return []

    db = await database.get_connection()
    try:
        # Step 1: Fetch all memories
        cursor = await db.execute(
            "SELECT id, content, context FROM memories"
        )
        rows = await cursor.fetchall()
        memories = [dict(row) for row in rows]

        if not memories:
            return []

        # Step 2: Build set of existing links (normalized)
        cursor = await db.execute(
            "SELECT source_memory_id, target_memory_id FROM memory_links"
        )
        link_rows = await cursor.fetchall()
        existing_links = set()
        for row in link_rows:
            # Normalize to (min, max) ordering to catch bidirectional links
            pair = tuple(sorted([row[0], row[1]]))
            existing_links.add(pair)

        # Step 3-4: Find candidates
        candidates = {}  # {(id_a, id_b): similarity}

        for memory in memories:
            # Build search text
            text = embeddings._build_embed_text(memory["content"], memory["context"])

            # Get top-10 semantic neighbors
            similar = await embeddings.semantic_search(text, limit=10)

            for similar_id, similarity in similar:
                # Filter: threshold, not self, no existing link
                if similarity < threshold:
                    continue
                if similar_id == memory["id"]:
                    continue

                # Normalize pair
                pair = tuple(sorted([memory["id"], similar_id]))
                if pair in existing_links:
                    continue

                # Keep highest similarity for this pair
                if pair not in candidates or similarity > candidates[pair]:
                    candidates[pair] = similarity

        # Step 5-6: Sort by similarity descending
        pairs = [(a, b, sim) for (a, b), sim in candidates.items()]
        pairs.sort(key=lambda x: x[2], reverse=True)

        return pairs

    except Exception as e:
        logger.error(f"Error finding unlinked pairs: {e}")
        return []
    finally:
        await db.close()


async def suggest_links(limit: int = 10) -> list[dict]:
    """Non-destructive suggestion of potential links.

    Returns suggested links without creating them. Useful for review
    before batch auto-linking.

    Args:
        limit: Maximum number of suggestions to return.

    Returns:
        List of dicts with keys:
        - source_id: First memory ID
        - target_id: Second memory ID
        - similarity: Similarity score (0.0-1.0)
        - source_content: First 100 chars of source memory
        - target_content: First 100 chars of target memory
    """
    try:
        pairs = await _find_unlinked_pairs(threshold=0.80)
        if not pairs:
            return []

        # Fetch memory content for preview
        db = await database.get_connection()
        try:
            suggestions = []
            for source_id, target_id, similarity in pairs[:limit]:
                # Fetch source content
                cursor = await db.execute(
                    "SELECT content FROM memories WHERE id = ?",
                    (source_id,)
                )
                source_row = await cursor.fetchone()
                source_content = source_row[0] if source_row else ""

                # Fetch target content
                cursor = await db.execute(
                    "SELECT content FROM memories WHERE id = ?",
                    (target_id,)
                )
                target_row = await cursor.fetchone()
                target_content = target_row[0] if target_row else ""

                suggestions.append({
                    "source_id": source_id,
                    "target_id": target_id,
                    "similarity": round(similarity, 4),
                    "source_content": source_content[:100],
                    "target_content": target_content[:100],
                })

            return suggestions
        finally:
            await db.close()

    except Exception as e:
        logger.error(f"Error suggesting links: {e}")
        return []


async def infer_links(
    similarity_threshold: float = 0.80,
    max_new_links: int = 20
) -> dict:
    """Batch process: find and create auto-inferred links.

    Fire-and-forget philosophy: never crash, always return stats.

    Algorithm:
    1. Find all high-similarity pairs without existing links
    2. Create 'related' links with strength = similarity
    3. Cap at max_new_links
    4. Return statistics

    Args:
        similarity_threshold: Minimum similarity (0.0-1.0) to create link.
        max_new_links: Maximum number of new links to create.

    Returns:
        Dict with keys:
        - status: "completed" or "error"
        - scanned: Number of memory pairs scanned
        - created: Number of new links created
        - skipped_existing: Number of pairs already linked
    """
    try:
        # Step 1: Find candidates
        pairs = await _find_unlinked_pairs(threshold=similarity_threshold)

        scanned = len(pairs)
        created = 0
        skipped_existing = 0

        if not pairs:
            return {
                "status": "completed",
                "scanned": 0,
                "created": 0,
                "skipped_existing": 0,
            }

        # Step 2-3: Create links (capped)
        db = await database.get_connection()
        try:
            now = _now()

            for source_id, target_id, similarity in pairs[:max_new_links]:
                # Double-check link doesn't exist (defense in depth)
                cursor = await db.execute(
                    """
                    SELECT 1 FROM memory_links
                    WHERE (source_memory_id = ? AND target_memory_id = ?)
                       OR (source_memory_id = ? AND target_memory_id = ?)
                    """,
                    (source_id, target_id, target_id, source_id)
                )
                exists = await cursor.fetchone()

                if exists:
                    skipped_existing += 1
                    continue

                # Create the link
                await db.execute(
                    """
                    INSERT OR IGNORE INTO memory_links
                    (source_memory_id, target_memory_id, link_type, strength, source, created_at)
                    VALUES (?, ?, 'related', ?, 'auto-inferred', ?)
                    """,
                    (source_id, target_id, similarity, now)
                )
                created += 1

            await db.commit()

            logger.info(
                f"Auto-linker completed: scanned={scanned}, created={created}, skipped={skipped_existing}"
            )

            return {
                "status": "completed",
                "scanned": scanned,
                "created": created,
                "skipped_existing": skipped_existing,
            }

        finally:
            await db.close()

    except Exception as e:
        logger.error(f"Auto-linker failed: {e}")
        return {
            "status": "error",
            "scanned": 0,
            "created": 0,
            "skipped_existing": 0,
            "error": str(e),
        }
