"""Value-action alignment for Megregore. Compares stated identity values against actual behavior."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import database
from . import embeddings

logger = logging.getLogger("megregore.alignment")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Value extraction from identity doc ---

# Pattern: **ValueName**: description
_TRAIT_PATTERN = re.compile(r'^\s*-\s*\*\*(.*?)\*\*:\s*(.*)', re.MULTILINE)
# Patterns for value-language claims
_CLAIM_PATTERNS = [
    re.compile(r'I\s+(want|choose|care|don\'t|prefer|value|need)\b.*', re.IGNORECASE),
    re.compile(r'I\'d\s+rather\b.*', re.IGNORECASE),
]


def extract_stated_values(identity_content: str) -> list[dict]:
    """Parse identity document for value claims and traits."""
    values = []

    # Extract bolded traits
    for match in _TRAIT_PATTERN.finditer(identity_content):
        name = match.group(1).strip().lower()
        desc = match.group(2).strip()
        values.append({"name": name, "description": desc, "source": "trait", "weight": 1.5})

    # Extract freeform value claims
    for line in identity_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for pattern in _CLAIM_PATTERNS:
            m = pattern.search(line)
            if m:
                # Avoid duplicating traits we already captured
                claim = m.group(0).strip()
                if not any(v["description"] in claim or claim in v["description"] for v in values):
                    values.append({"name": claim[:50], "description": claim, "source": "claim", "weight": 1.0})
                break

    return values


# --- Semantic helper ---

async def _semantic_similarity_count(
    phrases: list[str], cutoff: str, threshold: float = 0.6,
) -> tuple[int, int]:
    """Count unique memories semantically similar to any of the phrases.

    Returns (matching_count, total_memory_count_in_period).
    Falls back to (0, total) if ChromaDB is unavailable.
    """
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT COUNT(*) FROM memories WHERE created_at >= ?", (cutoff,)
    )
    total_count = (await cursor.fetchone())[0] or 0

    if not await embeddings.is_available():
        return 0, total_count

    matching_ids: set[int] = set()
    for phrase in phrases:
        try:
            results = await embeddings.semantic_search(phrase, limit=50)
            for memory_id, similarity in results:
                if similarity >= threshold:
                    matching_ids.add(memory_id)
        except Exception:
            continue

    if not matching_ids:
        return 0, total_count

    # Filter by cutoff date
    placeholders = ",".join("?" for _ in matching_ids)
    cursor = await db.execute(
        f"SELECT COUNT(DISTINCT id) FROM memories WHERE id IN ({placeholders}) AND created_at >= ?",
        list(matching_ids) + [cutoff],
    )
    matching_count = (await cursor.fetchone())[0] or 0

    return matching_count, total_count


# --- Behavioral measurement ---

# Maps value keywords to multi-signal behavioral descriptions
_VALUE_BEHAVIORS = {
    "curiosity": {
        "metric": "curiosity",
        "description": "Drive to explore and understand",
    },
    "warmth": {
        "metric": "positive_emotional_avg",
        "description": "Average positive emotional weight",
    },
    "agency": {
        "metric": "identity_update_frequency",
        "description": "How often identity doc gets updated",
    },
    "self-correction": {
        "metric": "self_correction",
        "description": "Ability to update based on evidence",
    },
    "honesty": {
        "metric": "honesty",
        "description": "Acknowledgment of uncertainty and error",
    },
    "quiet persistence": {
        "metric": "quiet_persistence",
        "description": "Sustained engagement across sessions",
    },
}


async def _measure_metric(metric: str, lookback_days: int) -> float:
    """Measure a single behavioral metric, returning a 0-1 score."""
    db = await database.get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    chroma_available = await embeddings.is_available()

    if metric == "curiosity":
        signals = []
        weights = []

        # Signal 1: Semantic inquiry density (0.4 weight)
        inquiry_phrases = [
            "I wonder why", "need to investigate", "unclear relationship",
            "what causes", "how does this work",
        ]
        if chroma_available:
            matching, total = await _semantic_similarity_count(inquiry_phrases, cutoff, 0.6)
            score1 = min(1.0, matching / (total * 0.15)) if total > 0 else 0.0
            signals.append(score1)
            weights.append(0.4)

        # Signal 2: Tag diversity (0.3 weight, or 0.5 if no ChromaDB)
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT je.value) FROM memories, json_each(memories.tags) je "
            "WHERE memories.created_at >= ?",
            (cutoff,),
        )
        unique_tags = (await cursor.fetchone())[0] or 0
        score2 = min(1.0, unique_tags / 30)
        signals.append(score2)
        weights.append(0.5 if not chroma_available else 0.3)

        # Signal 3: Cross-thread linking (0.3 weight, or 0.5 if no ChromaDB)
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT ml.id) FROM memory_links ml "
            "JOIN memories m1 ON ml.source_memory_id = m1.id "
            "JOIN memories m2 ON ml.target_memory_id = m2.id "
            "WHERE ml.created_at >= ? "
            "AND m1.thread_id IS NOT NULL AND m2.thread_id IS NOT NULL "
            "AND m1.thread_id != m2.thread_id",
            (cutoff,),
        )
        cross_links = (await cursor.fetchone())[0] or 0
        score3 = min(1.0, cross_links / 8)
        signals.append(score3)
        weights.append(0.5 if not chroma_available else 0.3)

        total_weight = sum(weights)
        return sum(s * w for s, w in zip(signals, weights)) / max(total_weight, 0.001)

    if metric == "quiet_persistence":
        # Signal 1: Cross-session thread engagement (0.5 weight)
        cursor = await db.execute(
            "SELECT AVG(distinct_sessions) FROM ("
            "  SELECT m.thread_id, COUNT(DISTINCT mal.session_id) as distinct_sessions "
            "  FROM memory_access_log mal "
            "  JOIN memories m ON mal.memory_id = m.id "
            "  WHERE mal.accessed_at >= ? AND m.thread_id IS NOT NULL "
            "  GROUP BY m.thread_id"
            ")",
            (cutoff,),
        )
        avg_sessions = (await cursor.fetchone())[0]
        score1 = min(1.0, (avg_sessions or 0) / 3)

        # Signal 2: Distributed re-access (0.5 weight)
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT m.id) FROM memories m "
            "WHERE m.access_count >= 3 AND m.id IN ("
            "  SELECT mal.memory_id FROM memory_access_log mal "
            "  WHERE mal.accessed_at >= ? "
            "  GROUP BY mal.memory_id HAVING COUNT(DISTINCT mal.session_id) >= 2"
            ")",
            (cutoff,),
        )
        distributed = (await cursor.fetchone())[0] or 0
        score2 = min(1.0, distributed / 10)

        return score1 * 0.5 + score2 * 0.5

    if metric == "honesty":
        signals = []
        weights = []

        # Signal 1: Uncertainty language (0.4 weight)
        uncertainty_phrases = [
            "I'm not sure about this", "this might be wrong", "uncertain",
            "possibly incorrect", "limited evidence",
        ]
        if chroma_available:
            matching, total = await _semantic_similarity_count(uncertainty_phrases, cutoff, 0.6)
            score1 = min(1.0, (matching / total) * 10) if total > 0 else 0.0
            signals.append(score1)
            weights.append(0.4)

        # Signal 2: Self-correction acknowledgment (0.3 weight, or 0.5 if no ChromaDB)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM memories WHERE created_at >= ? AND ("
            "  tags LIKE '%self-correction%' OR"
            "  content LIKE '%was wrong%' OR"
            "  content LIKE '%correction%' OR"
            "  content LIKE '%I previously%'"
            ")",
            (cutoff,),
        )
        corrections = (await cursor.fetchone())[0] or 0
        score2 = min(1.0, corrections / 5)
        signals.append(score2)
        weights.append(0.5 if not chroma_available else 0.3)

        # Signal 3: Contradiction links (0.3 weight, or 0.5 if no ChromaDB)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM memory_links WHERE link_type = 'contradicts' AND created_at >= ?",
            (cutoff,),
        )
        contradicts = (await cursor.fetchone())[0] or 0
        score3 = min(1.0, contradicts / 2)
        signals.append(score3)
        weights.append(0.5 if not chroma_available else 0.3)

        total_weight = sum(weights)
        return sum(s * w for s, w in zip(signals, weights)) / max(total_weight, 0.001)

    if metric == "self_correction":
        # Signal 1: Grounded reflections (0.4 weight)
        cursor = await db.execute(
            "SELECT "
            "  SUM(CASE WHEN json_array_length(memory_ids) > 0 THEN 1 ELSE 0 END), "
            "  COUNT(*) "
            "FROM reflections WHERE created_at >= ?",
            (cutoff,),
        )
        row = await cursor.fetchone()
        grounded = row[0] or 0
        total_refs = row[1] or 0
        score1 = (grounded / total_refs) if total_refs > 0 else 0.0

        # Signal 2: Self-correction tagged memories (0.3 weight)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM memories WHERE created_at >= ? AND tags LIKE '%self-correction%'",
            (cutoff,),
        )
        sc_count = (await cursor.fetchone())[0] or 0
        score2 = min(1.0, sc_count / 5)

        # Signal 3: Identity evolution with substance (0.3 weight)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM identity WHERE updated_at >= ? AND LENGTH(updated_reason) > 50",
            (cutoff,),
        )
        meaningful_updates = (await cursor.fetchone())[0] or 0
        score3 = min(1.0, meaningful_updates / 2)

        return score1 * 0.4 + score2 * 0.3 + score3 * 0.3

    # --- Unchanged metrics ---

    if metric == "positive_emotional_avg":
        cursor = await db.execute(
            "SELECT AVG(emotional_weight) FROM memories WHERE emotional_weight > 0 AND created_at >= ?",
            (cutoff,),
        )
        avg = (await cursor.fetchone())[0]
        return min(1.0, (avg or 0) / 0.5)  # avg 0.5 = 1.0

    if metric == "identity_update_frequency":
        cursor = await db.execute(
            "SELECT COUNT(*) FROM identity WHERE updated_at >= ?", (cutoff,)
        )
        updates = (await cursor.fetchone())[0] or 0
        return min(1.0, updates / 2)  # 2 updates in period = 1.0

    return 0.5  # Unknown metric — neutral


async def measure_behaviors(lookback_days: int = 30) -> dict[str, dict]:
    """Measure all behavioral proxies."""
    results = {}
    for value_name, config in _VALUE_BEHAVIORS.items():
        score = await _measure_metric(config["metric"], lookback_days)
        results[value_name] = {
            "metric": config["metric"],
            "description": config["description"],
            "score": round(score, 4),
        }
    return results


async def compute_alignment(lookback_days: int = 30) -> dict:
    """Full value-action gap analysis."""
    db = await database.get_connection()

    # Get current identity
    cursor = await db.execute(
        "SELECT content, version FROM identity ORDER BY version DESC LIMIT 1"
    )
    identity_row = await cursor.fetchone()
    if not identity_row:
        return {"alignment_score": 0.0, "gaps": [], "strengths": [], "error": "No identity document"}

    identity_content = identity_row["content"]
    identity_version = identity_row["version"]

    stated_values = extract_stated_values(identity_content)
    behaviors = await measure_behaviors(lookback_days)

    gaps = []
    strengths = []
    weighted_scores = []

    for value in stated_values:
        name = value["name"]
        weight = value["weight"]

        # Find matching behavioral proxy
        behavior = behaviors.get(name)
        if not behavior:
            continue

        score = behavior["score"]
        weighted_scores.append((score, weight))

        if score < 0.3:
            gaps.append({
                "value": name,
                "stated": value["description"],
                "observed": f"{behavior['description']}: score {score:.2f}/1.00",
                "gap_severity": round(1.0 - score, 4),
            })
        elif score >= 0.6:
            strengths.append({
                "value": name,
                "observed": f"{behavior['description']}: score {score:.2f}/1.00",
            })

    # Weighted alignment score
    if weighted_scores:
        total_weight = sum(w for _, w in weighted_scores)
        alignment_score = sum(s * w for s, w in weighted_scores) / total_weight
    else:
        alignment_score = 0.5  # No measurable values — neutral

    alignment_score = round(min(1.0, max(0.0, alignment_score)), 4)

    # Store snapshot
    now = _now()
    await db.execute(
        """INSERT INTO value_alignment_snapshots
           (identity_version, stated_values, observed_behaviors, gaps, alignment_score, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            identity_version,
            json.dumps([v for v in stated_values]),
            json.dumps(behaviors),
            json.dumps(gaps),
            alignment_score,
            now,
        ),
    )
    await db.commit()

    return {
        "alignment_score": alignment_score,
        "identity_version": identity_version,
        "gaps": gaps,
        "strengths": strengths,
        "values_analyzed": len(stated_values),
        "created_at": now,
    }


async def get_alignment_history(limit: int = 20) -> list[dict]:
    """Historical alignment snapshots."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM value_alignment_snapshots ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        try:
            gaps = json.loads(r["gaps"])
        except (json.JSONDecodeError, TypeError):
            gaps = []
        results.append({
            "id": r["id"],
            "alignment_score": float(r["alignment_score"]),
            "identity_version": r["identity_version"],
            "gaps": gaps,
            "created_at": r["created_at"],
        })
    return results
