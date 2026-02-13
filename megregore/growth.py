"""Growth metrics for Megregore. Measures integration, contradiction resolution, and trajectory."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database

logger = logging.getLogger("megregore.growth")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def compute_integration_score() -> float:
    """
    Weighted composite integration score (0-1).

    Components: link_density (0.30), thread_coverage (0.25),
    consolidation_ratio (0.20), cross_thread_ratio (0.15),
    emotional_range (0.10).
    """
    db = await database.get_connection()

    cursor = await db.execute("SELECT COUNT(*) FROM memories")
    total_memories = (await cursor.fetchone())[0] or 0
    if total_memories == 0:
        return 0.0

    cursor = await db.execute("SELECT COUNT(*) FROM memory_links")
    total_links = (await cursor.fetchone())[0] or 0

    cursor = await db.execute(
        "SELECT COUNT(*) FROM memories WHERE thread_id IS NOT NULL"
    )
    threaded = (await cursor.fetchone())[0] or 0

    cursor = await db.execute(
        "SELECT COUNT(*) FROM reflections WHERE insight_type = 'consolidation'"
    )
    consolidations = (await cursor.fetchone())[0] or 0

    cursor = await db.execute("""
        SELECT COUNT(*) FROM memory_links ml
        JOIN memories m1 ON ml.source_memory_id = m1.id
        JOIN memories m2 ON ml.target_memory_id = m2.id
        WHERE m1.thread_id IS NOT NULL AND m2.thread_id IS NOT NULL
          AND m1.thread_id != m2.thread_id
    """)
    cross_thread = (await cursor.fetchone())[0] or 0

    cursor = await db.execute(
        "SELECT MIN(emotional_weight), MAX(emotional_weight) FROM memories"
    )
    row = await cursor.fetchone()
    min_e, max_e = (row[0] or 0.0), (row[1] or 0.0)

    link_density = min(1.0, (total_links / total_memories) / 3.0)
    thread_cov = threaded / total_memories
    consol_ratio = min(1.0, consolidations / max(total_memories * 0.1, 1))
    cross_ratio = min(1.0, cross_thread / max(total_links, 1))
    emotional_range_score = min(1.0, (max_e - min_e) / 2.0)

    score = (
        link_density * 0.30
        + thread_cov * 0.25
        + consol_ratio * 0.20
        + cross_ratio * 0.15
        + emotional_range_score * 0.10
    )
    return round(score, 4)


async def check_contradiction_resolutions() -> dict:
    """Find contradictions resolved through consolidation. Returns {checked, newly_resolved}."""
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT id, source_memory_id, target_memory_id FROM memory_links "
        "WHERE link_type = 'contradicts' AND resolved = 0"
    )
    unresolved = await cursor.fetchall()
    if not unresolved:
        return {"checked": 0, "newly_resolved": 0}

    # Load consolidation reflections and their memory_ids
    cursor = await db.execute(
        "SELECT id, memory_ids FROM reflections WHERE insight_type = 'consolidation'"
    )
    consolidations = await cursor.fetchall()

    # Parse memory_ids for each consolidation
    parsed = []
    for r in consolidations:
        try:
            ids = set(json.loads(r["memory_ids"]))
            parsed.append((r["id"], ids))
        except (json.JSONDecodeError, TypeError):
            continue

    newly_resolved = 0
    for link in unresolved:
        source_id = link["source_memory_id"]
        target_id = link["target_memory_id"]

        # Check if both appear in any consolidation
        for ref_id, mem_ids in parsed:
            if source_id in mem_ids and target_id in mem_ids:
                await db.execute(
                    "UPDATE memory_links SET resolved = 1, resolved_at = ?, resolved_by_id = ? WHERE id = ?",
                    (_now(), ref_id, link["id"]),
                )
                newly_resolved += 1
                break

    if newly_resolved:
        await db.commit()
        logger.info("Resolved %d contradiction links", newly_resolved)

    return {"checked": len(unresolved), "newly_resolved": newly_resolved}


async def compute_growth_snapshot(session_id: Optional[str] = None) -> dict:
    """Compute all growth metrics and store a new snapshot."""
    db = await database.get_connection()

    # Counts
    cursor = await db.execute("SELECT COUNT(*) FROM memories")
    total_memories = (await cursor.fetchone())[0] or 0

    cursor = await db.execute("SELECT COUNT(*) FROM memory_links")
    total_links = (await cursor.fetchone())[0] or 0

    # Contradiction metrics
    cursor = await db.execute(
        "SELECT COUNT(*) FROM memory_links WHERE link_type = 'contradicts'"
    )
    total_contradictions = (await cursor.fetchone())[0] or 0

    cursor = await db.execute(
        "SELECT COUNT(*) FROM memory_links WHERE link_type = 'contradicts' AND resolved = 1"
    )
    resolved_contradictions = (await cursor.fetchone())[0] or 0

    resolution_rate = (
        resolved_contradictions / total_contradictions if total_contradictions > 0 else 0.0
    )

    integration_score = await compute_integration_score()

    avg_links = total_links / max(total_memories, 1)

    cursor = await db.execute(
        "SELECT COUNT(*) FROM memories WHERE thread_id IS NOT NULL"
    )
    threaded = (await cursor.fetchone())[0] or 0
    thread_cov = threaded / max(total_memories, 1)

    cursor = await db.execute(
        "SELECT COUNT(*) FROM reflections WHERE insight_type = 'consolidation'"
    )
    consolidations = (await cursor.fetchone())[0] or 0
    consol_ratio = consolidations / max(total_memories, 1)

    # Unique tags (flatten JSON arrays)
    cursor = await db.execute("SELECT tags FROM memories WHERE tags IS NOT NULL AND tags != '[]'")
    all_tags = set()
    async for row in cursor:
        try:
            for tag in json.loads(row[0]):
                all_tags.add(tag)
        except (json.JSONDecodeError, TypeError):
            pass
    unique_topics = len(all_tags)

    # Cross-thread links
    cursor = await db.execute("""
        SELECT COUNT(*) FROM memory_links ml
        JOIN memories m1 ON ml.source_memory_id = m1.id
        JOIN memories m2 ON ml.target_memory_id = m2.id
        WHERE m1.thread_id IS NOT NULL AND m2.thread_id IS NOT NULL
          AND m1.thread_id != m2.thread_id
    """)
    cross_thread = (await cursor.fetchone())[0] or 0

    # Emotional range
    cursor = await db.execute(
        "SELECT MIN(emotional_weight), MAX(emotional_weight) FROM memories"
    )
    row = await cursor.fetchone()
    emotional_range = (row[1] or 0.0) - (row[0] or 0.0)

    # Delta from previous snapshot
    cursor = await db.execute(
        "SELECT integration_score FROM growth_snapshots ORDER BY created_at DESC LIMIT 1"
    )
    prev = await cursor.fetchone()
    integration_delta = integration_score - prev[0] if prev else 0.0

    now = _now()
    snapshot = {
        "total_contradictions": total_contradictions,
        "resolved_contradictions": resolved_contradictions,
        "resolution_rate": round(resolution_rate, 4),
        "integration_score": integration_score,
        "avg_links_per_memory": round(avg_links, 2),
        "thread_coverage_pct": round(thread_cov, 4),
        "consolidation_ratio": round(consol_ratio, 4),
        "unique_topic_count": unique_topics,
        "cross_thread_link_count": cross_thread,
        "emotional_range": round(emotional_range, 2),
        "integration_delta": round(integration_delta, 4),
        "session_id": session_id,
        "created_at": now,
    }

    await db.execute(
        """INSERT INTO growth_snapshots
           (total_contradictions, resolved_contradictions, resolution_rate,
            integration_score, avg_links_per_memory, thread_coverage_pct,
            consolidation_ratio, unique_topic_count, cross_thread_link_count,
            emotional_range, integration_delta, session_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            total_contradictions, resolved_contradictions, round(resolution_rate, 4),
            integration_score, round(avg_links, 2), round(thread_cov, 4),
            round(consol_ratio, 4), unique_topics, cross_thread,
            round(emotional_range, 2), round(integration_delta, 4), session_id, now,
        ),
    )
    await db.commit()
    logger.info("Growth snapshot created: integration_score=%.4f", integration_score)
    return snapshot


async def get_growth_trajectory(limit: int = 20) -> list[dict]:
    """Retrieve recent growth snapshots, most recent first."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM growth_snapshots ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def should_generate_snapshot() -> bool:
    """True if last snapshot is older than 3 days or none exist."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT created_at FROM growth_snapshots ORDER BY created_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    if not row:
        return True
    created = datetime.fromisoformat(row[0])
    elapsed = datetime.now(timezone.utc) - created
    return elapsed.days >= 3
