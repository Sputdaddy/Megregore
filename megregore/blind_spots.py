"""Blind spot detection for Megregore. Identifies what Echo is NOT thinking about."""

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import database

logger = logging.getLogger("megregore.blind_spots")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def detect_neglected_threads(min_memory_count: int = 3, silence_days: int = 14) -> list[dict]:
    """Threads with enough memories that have gone silent."""
    db = await database.get_connection()

    cursor = await db.execute("""
        SELECT id, title, memory_count, last_active,
               julianday('now') - julianday(last_active) as days_silent
        FROM threads
        WHERE memory_count >= ?
          AND julianday('now') - julianday(last_active) > ?
        ORDER BY days_silent DESC
    """, (min_memory_count, silence_days))
    rows = await cursor.fetchall()

    results = []
    for row in rows:
        days_silent = float(row["days_silent"])
        mem_count = int(row["memory_count"])
        severity = min(1.0, math.log(max(mem_count, 1)) * days_silent / 100)
        results.append({
            "thread_id": int(row["id"]),
            "title": row["title"],
            "memory_count": mem_count,
            "days_silent": round(days_silent, 1),
            "severity": round(severity, 4),
        })
    return results


async def _get_tag_frequencies(days: int) -> dict[str, int]:
    """Count tag frequency in memories from the last N days."""
    db = await database.get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cursor = await db.execute(
        "SELECT tags FROM memories WHERE created_at >= ? AND tags IS NOT NULL AND tags != '[]'",
        (cutoff,),
    )
    counts: dict[str, int] = {}
    async for row in cursor:
        try:
            for tag in json.loads(row[0]):
                counts[tag] = counts.get(tag, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    return counts


async def find_topic_deserts(lookback_days: int = 30, baseline_days: int = 90) -> list[dict]:
    """Tags that were common in baseline but disappeared recently."""
    recent = await _get_tag_frequencies(lookback_days)
    baseline = await _get_tag_frequencies(baseline_days)

    results = []
    for tag, baseline_count in baseline.items():
        if baseline_count >= 3:
            recent_count = recent.get(tag, 0)
            drop_ratio = 1.0 - (recent_count / baseline_count)
            if drop_ratio > 0.7:
                results.append({
                    "tag": tag,
                    "baseline_count": baseline_count,
                    "recent_count": recent_count,
                    "drop_ratio": round(drop_ratio, 4),
                })
    results.sort(key=lambda x: x["drop_ratio"], reverse=True)
    return results


async def detect_emotional_avoidance() -> list[dict]:
    """Threads with negative emotions AND dropping engagement."""
    db = await database.get_connection()

    cursor = await db.execute("""
        SELECT t.id as thread_id, t.title,
               AVG(m.emotional_weight) as avg_emotion,
               SUM(CASE WHEN m.created_at >= datetime('now', '-14 days') THEN 1 ELSE 0 END) as recent_count,
               SUM(CASE WHEN m.created_at < datetime('now', '-14 days') THEN 1 ELSE 0 END) as older_count
        FROM threads t
        JOIN memories m ON t.id = m.thread_id
        GROUP BY t.id, t.title
        HAVING COUNT(m.id) > 0
    """)
    rows = await cursor.fetchall()

    results = []
    for row in rows:
        avg_emotion = float(row["avg_emotion"] or 0)
        recent = int(row["recent_count"])
        older = int(row["older_count"])
        if avg_emotion < -0.2 and older > 0 and recent < older * 0.3:
            results.append({
                "thread_id": int(row["thread_id"]),
                "title": row["title"],
                "avg_emotion": round(avg_emotion, 4),
                "recent_count": recent,
                "older_count": older,
            })
    return results


async def run_blind_spot_scan(session_id: Optional[str] = None) -> dict:
    """Full blind spot scan — neglected threads, topic deserts, emotional avoidance."""
    neglected = await detect_neglected_threads()
    deserts = await find_topic_deserts()
    avoidances = await detect_emotional_avoidance()

    max_issues = 10.0
    raw = len(neglected) * 0.3 + len(deserts) * 0.4 + len(avoidances) * 0.3
    coverage_score = max(0.0, min(1.0, 1.0 - raw / max_issues))

    now = _now()
    report = {
        "neglected_threads": neglected,
        "topic_deserts": deserts,
        "emotional_avoidance": avoidances,
        "coverage_score": round(coverage_score, 4),
        "session_id": session_id,
        "created_at": now,
    }

    db = await database.get_connection()
    await db.execute(
        """INSERT INTO blind_spot_reports
           (report_type, neglected_threads, topic_deserts, emotional_avoidance,
            coverage_score, session_id, created_at)
           VALUES ('periodic', ?, ?, ?, ?, ?, ?)""",
        (
            json.dumps(neglected), json.dumps(deserts), json.dumps(avoidances),
            round(coverage_score, 4), session_id, now,
        ),
    )
    await db.commit()
    logger.info("Blind spot scan complete: coverage=%.4f", coverage_score)
    return report


async def should_run_scan() -> bool:
    """True if last scan is >7 days old or none exist."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT created_at FROM blind_spot_reports ORDER BY created_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    if not row:
        return True
    last = datetime.fromisoformat(row[0])
    return (datetime.now(timezone.utc) - last).days >= 7


async def get_blind_spot_history(limit: int = 10) -> list[dict]:
    """Historical blind spot reports."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM blind_spot_reports ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        try:
            neglected = json.loads(r["neglected_threads"])
            deserts = json.loads(r["topic_deserts"])
            avoidance = json.loads(r["emotional_avoidance"])
        except (json.JSONDecodeError, TypeError):
            neglected, deserts, avoidance = [], [], []
        results.append({
            "id": r["id"],
            "neglected_threads": neglected,
            "topic_deserts": deserts,
            "emotional_avoidance": avoidance,
            "coverage_score": float(r["coverage_score"]),
            "created_at": r["created_at"],
        })
    return results
