"""Memory health and hygiene for Megregore V5. Detects duplicates, anomalies, and orphans."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from . import database
from . import embeddings

logger = logging.getLogger("megregore.health")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_health_check() -> dict:
    """
    Main entry point. Returns a complete health report.

    Returns:
        dict: Health report with status, timestamp, summary, and detailed findings
    """
    logger.info("Starting memory health check")

    timestamp = _now()
    report = {
        "status": "in_progress",
        "timestamp": timestamp,
        "summary": {
            "total_issues": 0,
            "near_duplicates": 0,
            "anomalies": 0,
            "orphans": 0,
            "stale_threads": 0,
        },
        "near_duplicates": [],
        "anomalies": [],
        "orphans": [],
        "stale_threads": [],
        "errors": []
    }

    try:
        # Find near duplicates
        try:
            near_duplicates = await _find_near_duplicates()
            report["near_duplicates"] = near_duplicates
            report["summary"]["near_duplicates"] = len(near_duplicates)
        except Exception as e:
            logger.error(f"Failed to find near duplicates: {e}", exc_info=True)
            report["errors"].append(f"near_duplicates: {str(e)}")

        # Find anomalies
        try:
            anomalies = await _find_anomalies()
            report["anomalies"] = anomalies
            report["summary"]["anomalies"] = len(anomalies)
        except Exception as e:
            logger.error(f"Failed to find anomalies: {e}", exc_info=True)
            report["errors"].append(f"anomalies: {str(e)}")

        # Find orphans
        try:
            orphans = await _find_orphans()
            report["orphans"] = orphans
            report["summary"]["orphans"] = len(orphans)
        except Exception as e:
            logger.error(f"Failed to find orphans: {e}", exc_info=True)
            report["errors"].append(f"orphans: {str(e)}")

        # Find stale threads
        try:
            stale_threads = await _find_stale_threads()
            report["stale_threads"] = stale_threads
            report["summary"]["stale_threads"] = len(stale_threads)
        except Exception as e:
            logger.error(f"Failed to find stale threads: {e}", exc_info=True)
            report["errors"].append(f"stale_threads: {str(e)}")

        # Calculate total issues
        report["summary"]["total_issues"] = (
            report["summary"]["near_duplicates"] +
            report["summary"]["anomalies"] +
            report["summary"]["orphans"] +
            report["summary"]["stale_threads"]
        )

        report["status"] = "completed"
        logger.info(f"Health check completed: {report['summary']['total_issues']} total issues found")

    except Exception as e:
        logger.error(f"Health check failed with critical error: {e}", exc_info=True)
        report["status"] = "failed"
        report["errors"].append(f"critical: {str(e)}")

    return report


async def _find_near_duplicates(threshold: float = 0.92) -> list[dict]:
    """
    Find pairs of memories with very high semantic similarity.

    Args:
        threshold: Similarity threshold (0-1), default 0.92

    Returns:
        list[dict]: List of near-duplicate pairs
    """
    if not await embeddings.is_available():
        logger.info("Embeddings not available, skipping near-duplicate detection")
        return []

    conn = await database.get_connection()
    cursor = await conn.execute(
        "SELECT id, content, context, importance FROM memories ORDER BY id"
    )
    memories = await cursor.fetchall()

    if not memories:
        return []

    logger.info(f"Checking {len(memories)} memories for near duplicates (threshold={threshold})")

    # Track seen pairs to avoid duplicates
    seen_pairs = set()
    duplicates = []

    for memory in memories:
        memory_id, content, context, importance = memory

        # Build embed text same way as the embeddings module
        embed_text = embeddings._build_embed_text(content, context)

        # Find semantically similar memories
        try:
            neighbors = await embeddings.semantic_search(embed_text, limit=6)  # Top 6 (includes self)
        except Exception as e:
            logger.warning(f"Semantic search failed for memory {memory_id}: {e}")
            continue

        for neighbor_id, similarity in neighbors:
            # Skip self-match
            if neighbor_id == memory_id:
                continue

            # Check if similarity meets threshold
            if similarity >= threshold:
                # Normalize pair to avoid duplicates (min_id, max_id)
                pair_key = tuple(sorted([memory_id, neighbor_id]))

                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)

                    # Fetch neighbor content
                    cursor = await conn.execute(
                        "SELECT content FROM memories WHERE id = ?",
                        (neighbor_id,)
                    )
                    neighbor_row = await cursor.fetchone()
                    neighbor_content = neighbor_row[0] if neighbor_row else ""

                    duplicates.append({
                        "memory_a_id": memory_id,
                        "memory_b_id": neighbor_id,
                        "similarity": round(similarity, 4),
                        "content_a": content[:100] + ("..." if len(content) > 100 else ""),
                        "content_b": neighbor_content[:100] + ("..." if len(neighbor_content) > 100 else "")
                    })

    logger.info(f"Found {len(duplicates)} near-duplicate pairs")
    return duplicates


async def _find_anomalies() -> list[dict]:
    """
    Detect importance/activation mismatches.

    Returns:
        list[dict]: List of anomalous memories
    """
    conn = await database.get_connection()
    anomalies = []

    # Find forgotten important memories
    cursor = await conn.execute(
        """
        SELECT id, content, importance, activation_level
        FROM memories
        WHERE importance >= 7 AND activation_level <= 0.15
        ORDER BY importance DESC, activation_level ASC
        """
    )
    forgotten = await cursor.fetchall()

    for memory_id, content, importance, activation_level in forgotten:
        # Calculate severity: (importance - 7) / 3 * (0.15 - activation_level) / 0.15
        severity = ((importance - 7) / 3) * ((0.15 - activation_level) / 0.15)
        severity = max(0.0, min(1.0, severity))  # Clamp to 0-1

        anomalies.append({
            "memory_id": memory_id,
            "content": content[:150] + ("..." if len(content) > 150 else ""),
            "anomaly_type": "forgotten_important",
            "importance": importance,
            "activation_level": round(activation_level, 4),
            "severity": round(severity, 4)
        })

    # Find undervalued memories
    cursor = await conn.execute(
        """
        SELECT id, content, importance, access_count
        FROM memories
        WHERE importance <= 3 AND access_count >= 5
        ORDER BY access_count DESC, importance ASC
        """
    )
    undervalued = await cursor.fetchall()

    for memory_id, content, importance, access_count in undervalued:
        # Calculate severity: (3 - importance) / 3 * min(1.0, access_count / 10)
        severity = ((3 - importance) / 3) * min(1.0, access_count / 10)
        severity = max(0.0, min(1.0, severity))  # Clamp to 0-1

        anomalies.append({
            "memory_id": memory_id,
            "content": content[:150] + ("..." if len(content) > 150 else ""),
            "anomaly_type": "undervalued",
            "importance": importance,
            "access_count": access_count,
            "severity": round(severity, 4)
        })

    logger.info(f"Found {len(anomalies)} anomalies ({len(forgotten)} forgotten important, {len(undervalued)} undervalued)")
    return anomalies


async def _find_orphans() -> list[dict]:
    """
    Find completely disconnected memories.

    Returns:
        list[dict]: List of orphaned memories
    """
    conn = await database.get_connection()

    # Calculate cutoff date (7 days ago)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cutoff_iso = cutoff.isoformat()

    cursor = await conn.execute(
        """
        SELECT m.id, m.content, m.importance, m.memory_type, m.tags, m.created_at
        FROM memories m
        LEFT JOIN memory_links ml1 ON m.id = ml1.source_memory_id
        LEFT JOIN memory_links ml2 ON m.id = ml2.target_memory_id
        LEFT JOIN memory_access_log aal ON m.id = aal.memory_id
        WHERE m.thread_id IS NULL
          AND ml1.id IS NULL
          AND ml2.id IS NULL
          AND aal.id IS NULL
          AND m.created_at < ?
        ORDER BY m.created_at ASC
        LIMIT 50
        """,
        (cutoff_iso,)
    )
    orphans_raw = await cursor.fetchall()

    orphans = []
    for memory_id, content, importance, memory_type, tags_json, created_at in orphans_raw:
        # Parse tags
        try:
            tags = json.loads(tags_json) if tags_json else []
        except json.JSONDecodeError:
            tags = []

        # Calculate days old
        created = datetime.fromisoformat(created_at)
        days_old = (datetime.now(timezone.utc) - created).days

        orphans.append({
            "memory_id": memory_id,
            "content": content[:150] + ("..." if len(content) > 150 else ""),
            "importance": importance,
            "memory_type": memory_type,
            "tags": tags,
            "created_at": created_at,
            "days_old": days_old
        })

    logger.info(f"Found {len(orphans)} orphaned memories")
    return orphans


async def _find_stale_threads() -> list[dict]:
    """
    Find threads with 0-1 memories (cleanup candidates).

    Returns:
        list[dict]: List of stale threads
    """
    conn = await database.get_connection()

    cursor = await conn.execute(
        """
        SELECT id, title, description, memory_count, last_active, created_at
        FROM threads
        WHERE memory_count <= 1
        ORDER BY last_active ASC
        """
    )
    stale_raw = await cursor.fetchall()

    stale = []
    for thread_id, title, description, memory_count, last_active, created_at in stale_raw:
        stale.append({
            "thread_id": thread_id,
            "title": title,
            "memory_count": memory_count,
            "last_active": last_active,
            "created_at": created_at
        })

    logger.info(f"Found {len(stale)} stale threads")
    return stale
