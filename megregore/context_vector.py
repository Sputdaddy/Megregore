"""Conversation-aware recall — session context vector for V11."""

import asyncio
import json
import logging
from typing import Optional

from . import database
from . import embeddings

logger = logging.getLogger("megregore.context_vector")

# In-memory cache: session_id -> averaged embedding vector (list[float])
_session_context_cache: dict[str, list[float]] = {}

# Configurable weights
SEARCH_WEIGHT = 0.7
CONTEXT_WEIGHT = 0.3
MAX_CONTEXT_MEMORIES = 10


async def compute_session_context_vector(session_id: str) -> Optional[list[float]]:
    """
    Compute a session context vector by averaging embeddings of recently
    accessed/created memories this session.

    Returns None if no memories have been accessed or embeddings are unavailable.
    """
    if not await embeddings._ensure_model():
        return None

    db = await database.get_connection()
    try:
        # Get last N memory IDs accessed this session
        cursor = await db.execute(
            """SELECT DISTINCT memory_id FROM memory_access_log
               WHERE session_id = ?
               ORDER BY accessed_at DESC
               LIMIT ?""",
            (session_id, MAX_CONTEXT_MEMORIES),
        )
        access_rows = await cursor.fetchall()
        memory_ids = [row[0] for row in access_rows]

        # Also include memories created this session
        cursor = await db.execute(
            "SELECT id FROM memories WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, MAX_CONTEXT_MEMORIES),
        )
        created_rows = await cursor.fetchall()
        for row in created_rows:
            if row[0] not in memory_ids:
                memory_ids.append(row[0])

        memory_ids = memory_ids[:MAX_CONTEXT_MEMORIES]

        if not memory_ids:
            return None

        # Fetch content for these memories
        placeholders = ",".join("?" * len(memory_ids))
        cursor = await db.execute(
            f"SELECT id, content, context FROM memories WHERE id IN ({placeholders})",
            memory_ids,
        )
        rows = await cursor.fetchall()

        if not rows:
            return None

        # Compute embeddings and average
        loop = asyncio.get_running_loop()
        vectors = []
        for row in rows:
            text = embeddings._build_embed_text(row["content"], row["context"])
            vec = await loop.run_in_executor(
                None,
                lambda t=text: embeddings._model.encode(t).tolist(),
            )
            vectors.append(vec)

        if not vectors:
            return None

        # Average all vectors
        dim = len(vectors[0])
        avg = [0.0] * dim
        for vec in vectors:
            for i in range(dim):
                avg[i] += vec[i]
        for i in range(dim):
            avg[i] /= len(vectors)

        # Cache the result
        _session_context_cache[session_id] = avg

        return avg
    finally:
        await db.close()


def blend_context_score(
    search_score: float,
    session_relevance: Optional[float],
) -> float:
    """
    Blend search score with session context relevance.

    final_score = SEARCH_WEIGHT * search_score + CONTEXT_WEIGHT * session_relevance

    When no session context is available, search_score passes through unchanged.
    """
    if session_relevance is None:
        return search_score
    return SEARCH_WEIGHT * search_score + CONTEXT_WEIGHT * session_relevance


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def set_session_topic(
    topics: list[str],
    session_id: str,
) -> dict:
    """
    Seed the session context vector from topic keywords.

    Useful at session start to prime recall relevance before any
    memories have been accessed.
    """
    if not await embeddings._ensure_model():
        return {"status": "unavailable", "message": "Embedding model not loaded"}

    loop = asyncio.get_running_loop()
    topic_text = " ".join(topics)
    vec = await loop.run_in_executor(
        None,
        lambda: embeddings._model.encode(topic_text).tolist(),
    )
    _session_context_cache[session_id] = vec

    logger.info("Session topic set: %s (session=%s)", topics, session_id)
    return {
        "status": "topic_set",
        "topics": topics,
        "session_id": session_id,
    }
