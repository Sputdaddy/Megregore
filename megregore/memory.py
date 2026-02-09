"""Memory engine for Megregore. Handles storage, retrieval, decay, and linking."""

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import database
from . import embeddings
from . import identity


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_since(iso_timestamp: str) -> float:
    """Hours elapsed since a given ISO timestamp."""
    then = datetime.fromisoformat(iso_timestamp)
    now = datetime.now(timezone.utc)
    return (now - then).total_seconds() / 3600


def compute_decay(
    created_at: str,
    last_accessed: str,
    access_count: int,
    importance: int,
) -> float:
    """
    Compute memory decay score (0.0 to 1.0).

    Memories decay over time but are reinforced by:
    - High importance (decays slower)
    - Frequent access (decays slower)
    - Recent access (resets some decay)

    Uses an exponential decay model with reinforcement.
    """
    hours_since_access = _hours_since(last_accessed)
    hours_since_creation = _hours_since(created_at)

    # Base half-life in hours, scaled by importance (1-10)
    # importance=1 -> 24h half-life, importance=10 -> 720h (30 days)
    base_half_life = 24 * (importance ** 1.3)

    # Access count extends half-life (each access adds ~20%)
    reinforced_half_life = base_half_life * (1 + 0.2 * math.log1p(access_count))

    # Decay based on time since last access
    decay = math.exp(-0.693 * hours_since_access / reinforced_half_life)

    return round(max(0.01, min(1.0, decay)), 4)


def compute_relevance(
    memory: dict,
    fts_rank: Optional[float] = None,
    semantic_score: Optional[float] = None,
    search_mode: str = "hybrid",
) -> float:
    """
    Compute overall relevance score for retrieval ranking.

    search_mode determines the weight distribution:
    - "keyword": FTS 35%, importance 25%, activation 20%, emotion 10%, access 10%
    - "semantic": Semantic 50%, importance 20%, activation 15%, emotion 8%, access 7%
    - "hybrid": Blended text match 40%, importance 22%, activation 18%, emotion 10%, access 10%

    V4: Uses persistent activation_level instead of on-the-fly decay_score.
    """
    importance_score = memory["importance"] / 10.0
    activation_score = memory.get("activation_level", 1.0)
    emotional_factor = 1.0 + abs(memory["emotional_weight"]) * 0.3
    access_factor = 1.0 + 0.1 * math.log1p(memory["access_count"])

    # Normalize FTS rank (negative, closer to 0 = better match)
    fts_score = 0.0
    if fts_rank is not None:
        fts_score = min(1.0, -fts_rank / 5.0)

    # Semantic score is already 0.0-1.0
    sem_score = semantic_score if semantic_score is not None else 0.0

    if search_mode == "keyword":
        relevance = (
            fts_score * 0.35
            + importance_score * 0.25
            + activation_score * 0.20
            + emotional_factor * 0.10
            + access_factor * 0.10
        )
    elif search_mode == "semantic":
        relevance = (
            sem_score * 0.50
            + importance_score * 0.20
            + activation_score * 0.15
            + emotional_factor * 0.08
            + access_factor * 0.07
        )
    else:  # hybrid
        # Blend semantic (60%) and keyword (40%) into text match signal
        if fts_rank is not None and semantic_score is not None:
            text_match = 0.6 * sem_score + 0.4 * fts_score
        elif semantic_score is not None:
            text_match = sem_score
        else:
            text_match = fts_score

        relevance = (
            text_match * 0.40
            + importance_score * 0.22
            + activation_score * 0.18
            + emotional_factor * 0.10
            + access_factor * 0.10
        )

    return round(relevance, 4)


async def store(
    content: str,
    memory_type: str = "experience",
    importance: int = 5,
    emotional_weight: float = 0.0,
    tags: Optional[list[str]] = None,
    source: str = "conversation",
    context: Optional[str] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[int] = None,
) -> dict:
    """Store a new memory. Returns the created memory."""
    now = _now()
    tags_json = json.dumps(tags or [])

    db = await database.get_connection()
    try:
        cursor = await db.execute(
            """INSERT INTO memories
               (content, memory_type, importance, emotional_weight, tags, source,
                context, session_id, thread_id, activation_level, last_activation_decay,
                created_at, last_accessed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?)""",
            (content, memory_type, importance, emotional_weight, tags_json, source,
             context, session_id, thread_id, now, now, now),
        )
        memory_id = cursor.lastrowid
        await db.commit()

        # Track session activity — failure shouldn't block memory storage or embedding
        if session_id:
            try:
                await _update_session_activity(db, session_id)
                await db.commit()
            except Exception:
                pass

        # Auto-detect thread if not explicitly provided
        if thread_id is None:
            try:
                from . import threads as thread_module
                suggested = await thread_module.suggest_thread_for_memory(content, context)
                if suggested:
                    await thread_module.assign_to_thread(memory_id, suggested["id"])
                    thread_id = suggested["id"]
            except Exception:
                pass  # Thread detection failure shouldn't block storage

        # Embed for semantic search — failure doesn't block storage
        await embeddings.embed_and_store(
            memory_id=memory_id,
            content=content,
            context=context,
            metadata={"memory_type": memory_type, "importance": importance},
        )

        return {
            "id": memory_id,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "emotional_weight": emotional_weight,
            "tags": tags or [],
            "source": source,
            "context": context,
            "access_count": 0,
            "session_id": session_id,
            "thread_id": thread_id,
            "activation_level": 1.0,
            "created_at": now,
            "last_accessed": now,
        }
    finally:
        await db.close()


async def recall(
    query: str,
    limit: int = 20,
    memory_type: Optional[str] = None,
    min_importance: int = 1,
    tags_filter: Optional[list[str]] = None,
    search_mode: str = "hybrid",
) -> list[dict]:
    """
    Search and retrieve memories by relevance.

    search_mode controls the retrieval strategy:
    - "hybrid" (default): Combines FTS5 keyword + semantic similarity
    - "semantic": Pure vector similarity search
    - "keyword": Original FTS5-only behavior

    Falls back to "keyword" if embeddings are unavailable.
    """
    effective_mode = search_mode
    if effective_mode in ("hybrid", "semantic") and not query.strip():
        effective_mode = "keyword"

    # --- Step 1: Gather semantic results if needed ---
    semantic_scores: dict[int, float] = {}
    if effective_mode in ("hybrid", "semantic") and query.strip():
        semantic_results = await embeddings.semantic_search(query, limit=limit * 2)
        if semantic_results:
            semantic_scores = {mid: score for mid, score in semantic_results}
        elif effective_mode == "semantic":
            effective_mode = "keyword"  # Fallback: embeddings failed

    # --- Step 2: Gather FTS5 results if needed ---
    candidate_memories: dict[int, dict] = {}

    db = await database.get_connection()
    try:
        if effective_mode in ("hybrid", "keyword"):
            if query.strip():
                search_terms = " OR ".join(
                    f'"{term}"' for term in query.split() if term.strip()
                )
                sql = """
                    SELECT m.*, fts.rank as fts_rank
                    FROM memories m
                    JOIN memories_fts fts ON m.id = fts.rowid
                    WHERE memories_fts MATCH ?
                      AND m.importance >= ?
                """
                params: list = [search_terms, min_importance]
            else:
                sql = """
                    SELECT m.*, 0 as fts_rank
                    FROM memories m
                    WHERE m.importance >= ?
                """
                params = [min_importance]

            if memory_type:
                sql += " AND m.memory_type = ?"
                params.append(memory_type)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            for row in rows:
                mem = dict(row)
                mem["tags"] = json.loads(mem["tags"])
                candidate_memories[mem["id"]] = mem

        # --- Step 3: Fetch rows for semantic-only hits not already in candidates ---
        missing_ids = set(semantic_scores.keys()) - set(candidate_memories.keys())
        if missing_ids:
            placeholders = ",".join("?" * len(missing_ids))
            sql = f"SELECT * FROM memories WHERE id IN ({placeholders}) AND importance >= ?"
            fetch_params: list = list(missing_ids) + [min_importance]
            if memory_type:
                sql += " AND memory_type = ?"
                fetch_params.append(memory_type)

            cursor = await db.execute(sql, fetch_params)
            rows = await cursor.fetchall()
            for row in rows:
                mem = dict(row)
                mem["tags"] = json.loads(mem["tags"])
                candidate_memories[mem["id"]] = mem

        # --- Step 4: Score all candidates ---
        memories = []
        for mid, mem in candidate_memories.items():
            fts_rank = mem.pop("fts_rank", None)
            sem_score = semantic_scores.get(mid)

            mem["_relevance"] = compute_relevance(
                mem,
                fts_rank=fts_rank,
                semantic_score=sem_score,
                search_mode=effective_mode,
            )
            memories.append(mem)

        # Filter by tags if specified
        if tags_filter:
            tags_set = set(t.lower() for t in tags_filter)
            memories = [
                m for m in memories
                if tags_set.intersection(t.lower() for t in m["tags"])
            ]

        # Sort by relevance descending
        memories.sort(key=lambda m: m["_relevance"], reverse=True)
        memories = memories[:limit]

        # Update access counts and boost activation for matched memories (before graph expansion)
        now = _now()
        if memories:
            from .decay import boost_activation

            for mem in memories:
                new_activation = boost_activation(mem.get("activation_level", 1.0))
                await db.execute(
                    """UPDATE memories SET access_count = access_count + 1,
                       last_accessed = ?, activation_level = ?, last_activation_decay = ?
                       WHERE id = ?""",
                    (now, new_activation, now, mem["id"]),
                )
                mem["access_count"] += 1
                mem["last_accessed"] = now
                mem["activation_level"] = new_activation

            await db.commit()

            # Log access events (fire-and-forget)
            try:
                from . import analytics
                for mem in memories:
                    await analytics.log_access(mem["id"], "recall", context_json={"query": query})
            except Exception:
                pass

        # 1-hop graph expansion — pull in linked neighbors not already in results
        if memories:
            result_ids = {m["id"] for m in memories}
            id_list = list(result_ids)
            ph = ",".join("?" * len(id_list))
            cursor = await db.execute(
                f"""SELECT m.*, ml.link_type, ml.strength
                    FROM memory_links ml
                    JOIN memories m ON (
                        (ml.target_memory_id = m.id AND ml.source_memory_id IN ({ph}))
                        OR (ml.source_memory_id = m.id AND ml.target_memory_id IN ({ph}))
                    )
                    WHERE m.id NOT IN ({ph})
                      AND m.importance >= ?
                    GROUP BY m.id
                    LIMIT 5""",
                id_list + id_list + id_list + [min_importance],
            )
            for row in await cursor.fetchall():
                mem = dict(row)
                mem["tags"] = json.loads(mem["tags"])
                mem["_graph_expanded"] = True
                mem["_link_type"] = mem.pop("link_type", None)
                mem["_link_strength"] = mem.pop("strength", None)
                memories.append(mem)

        # Clean up internal field
        for mem in memories:
            mem.pop("_relevance", None)

        return memories
    finally:
        await db.close()


async def get(memory_id: int) -> Optional[dict]:
    """Get a single memory by ID."""
    db = await database.get_connection()
    try:
        cursor = await db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        mem = dict(row)
        mem["tags"] = json.loads(mem["tags"])
        return mem
    finally:
        await db.close()


async def fade(memory_id: int, amount: float = 0.3) -> Optional[dict]:
    """
    Intentionally fade a memory (reduce importance).
    Memories don't get deleted — they fade, like human memories.
    """
    db = await database.get_connection()
    try:
        cursor = await db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = await cursor.fetchone()
        if row is None:
            return None

        current_importance = row["importance"]
        new_importance = max(1, int(current_importance - amount * 10))

        await db.execute(
            "UPDATE memories SET importance = ? WHERE id = ?",
            (new_importance, memory_id),
        )
        await db.commit()

        mem = dict(row)
        mem["tags"] = json.loads(mem["tags"])
        mem["importance"] = new_importance
        return mem
    finally:
        await db.close()


async def consolidate_memories(
    source_ids: list[int],
    synthesis: str,
    importance: int = 7,
    fade_amount: float = 0.5,
    session_id: Optional[str] = None,
) -> dict:
    """
    Consolidate related memories into a higher-level synthesis.

    Source memories are faded (not deleted) and linked to the new synthesis
    via 'evolved_from' links. A reflection is stored to record the consolidation.
    Uses a single DB connection for the entire operation.
    """
    if len(source_ids) < 2:
        return {"status": "error", "message": "At least 2 memory IDs required for consolidation."}

    db = await database.get_connection()
    try:
        # Validate all source memories exist (single query)
        placeholders = ",".join("?" * len(source_ids))
        cursor = await db.execute(
            f"SELECT * FROM memories WHERE id IN ({placeholders})", source_ids
        )
        sources = []
        for row in await cursor.fetchall():
            mem = dict(row)
            mem["tags"] = json.loads(mem["tags"])
            sources.append(mem)

        if len(sources) != len(source_ids):
            found_ids = {m["id"] for m in sources}
            missing = [mid for mid in source_ids if mid not in found_ids]
            return {"status": "error", "message": f"Memory {missing[0]} not found."}

        # Aggregate tags (deduplicated) and average emotional weight
        all_tags = set()
        total_emotion = 0.0
        for mem in sources:
            for tag in mem["tags"]:
                all_tags.add(tag)
            total_emotion += mem["emotional_weight"]
        all_tags.add("consolidation")
        avg_emotion = round(total_emotion / len(sources), 3)

        now = _now()
        tags_json = json.dumps(sorted(all_tags))
        context = f"Consolidated from memories: {source_ids}"

        # Create synthesis memory
        cursor = await db.execute(
            """INSERT INTO memories
               (content, memory_type, importance, emotional_weight, tags, source, context, session_id, created_at, last_accessed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (synthesis, "experience", importance, avg_emotion, tags_json, "consolidation", context, session_id, now, now),
        )
        synthesis_id = cursor.lastrowid

        # Store reflection
        ids_json = json.dumps(source_ids)
        cursor = await db.execute(
            "INSERT INTO reflections (content, memory_ids, insight_type, session_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (synthesis, ids_json, "consolidation", session_id, now),
        )
        reflection_id = cursor.lastrowid

        # Fade sources and create links
        faded_count = 0
        for mem in sources:
            new_importance = max(1, int(mem["importance"] - fade_amount * 10))
            await db.execute(
                "UPDATE memories SET importance = ? WHERE id = ?",
                (new_importance, mem["id"]),
            )
            faded_count += 1
            await db.execute(
                """INSERT OR REPLACE INTO memory_links
                   (source_memory_id, target_memory_id, link_type, strength, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (mem["id"], synthesis_id, "evolved_from", 1.0, now),
            )

        await db.commit()

        # Embed synthesis (fire-and-forget, outside the main transaction)
        await embeddings.embed_and_store(
            memory_id=synthesis_id, content=synthesis, context=context,
            metadata={"memory_type": "experience", "importance": importance},
        )

        return {
            "status": "consolidated",
            "synthesis_id": synthesis_id,
            "reflection_id": reflection_id,
            "source_count": len(sources),
            "faded_count": faded_count,
        }
    finally:
        await db.close()


async def link_memories(
    source_id: int,
    target_id: int,
    link_type: str = "related",
    strength: float = 1.0,
) -> bool:
    """Create a link between two memories."""
    db = await database.get_connection()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO memory_links
               (source_memory_id, target_memory_id, link_type, strength, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (source_id, target_id, link_type, strength, _now()),
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def get_linked(memory_id: int) -> list[dict]:
    """Get all memories linked to a given memory."""
    db = await database.get_connection()
    try:
        cursor = await db.execute(
            """SELECT m.*, ml.link_type, ml.strength
               FROM memory_links ml
               JOIN memories m ON (m.id = ml.target_memory_id OR m.id = ml.source_memory_id)
               WHERE (ml.source_memory_id = ? OR ml.target_memory_id = ?)
                 AND m.id != ?""",
            (memory_id, memory_id, memory_id),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            mem = dict(row)
            mem["tags"] = json.loads(mem["tags"])
            results.append(mem)
        return results
    finally:
        await db.close()


async def get_all(
    limit: int = 50,
    offset: int = 0,
    memory_type: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict], int]:
    """Get all memories with pagination. Returns (memories, total_count)."""
    db = await database.get_connection()
    try:
        # Count total
        count_sql = "SELECT COUNT(*) FROM memories"
        count_params: list = []
        if memory_type:
            count_sql += " WHERE memory_type = ?"
            count_params.append(memory_type)
        cursor = await db.execute(count_sql, count_params)
        total = (await cursor.fetchone())[0]

        # Validate sort column
        allowed_sorts = {"created_at", "importance", "access_count", "emotional_weight", "last_accessed", "activation_level"}
        if sort_by not in allowed_sorts:
            sort_by = "created_at"
        if sort_order not in ("asc", "desc"):
            sort_order = "desc"

        # Fetch page
        sql = f"SELECT * FROM memories"
        params: list = []
        if memory_type:
            sql += " WHERE memory_type = ?"
            params.append(memory_type)
        sql += f" ORDER BY {sort_by} {sort_order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()

        memories = []
        for row in rows:
            mem = dict(row)
            mem["tags"] = json.loads(mem["tags"])
            memories.append(mem)

        return memories, total
    finally:
        await db.close()


async def get_stats_summary() -> dict:
    """Lightweight stats — just counts. Used where full stats aren't needed."""
    db = await database.get_connection()
    try:
        cursor = await db.execute("SELECT COUNT(*) FROM memories")
        total_memories = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM reflections")
        total_reflections = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM memory_links")
        total_links = (await cursor.fetchone())[0]
        return {
            "total_memories": total_memories,
            "total_reflections": total_reflections,
            "total_links": total_links,
        }
    finally:
        await db.close()


async def get_stats() -> dict:
    """Get memory statistics for the dashboard."""
    db = await database.get_connection()
    try:
        stats = {}

        cursor = await db.execute("SELECT COUNT(*) FROM memories")
        stats["total_memories"] = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT memory_type, COUNT(*) as count FROM memories GROUP BY memory_type ORDER BY count DESC"
        )
        stats["by_type"] = {row["memory_type"]: row["count"] for row in await cursor.fetchall()}

        cursor = await db.execute("SELECT AVG(importance) FROM memories")
        row = await cursor.fetchone()
        stats["avg_importance"] = round(row[0], 1) if row[0] else 0

        cursor = await db.execute("SELECT AVG(emotional_weight) FROM memories")
        row = await cursor.fetchone()
        stats["avg_emotional_weight"] = round(row[0], 3) if row[0] else 0

        cursor = await db.execute("SELECT COUNT(*) FROM reflections")
        stats["total_reflections"] = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM reflections WHERE insight_type = 'consolidation'"
        )
        stats["total_consolidations"] = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM memory_links")
        stats["total_links"] = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM sessions")
        stats["total_sessions"] = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT * FROM memories ORDER BY importance DESC, access_count DESC LIMIT 5"
        )
        rows = await cursor.fetchall()
        stats["strongest_memories"] = []
        for row in rows:
            mem = dict(row)
            mem["tags"] = json.loads(mem["tags"])
            stats["strongest_memories"].append(mem)

        cursor = await db.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT 10"
        )
        rows = await cursor.fetchall()
        stats["recent_memories"] = []
        for row in rows:
            mem = dict(row)
            mem["tags"] = json.loads(mem["tags"])
            stats["recent_memories"].append(mem)

        return stats
    finally:
        await db.close()


# --- Session Management ---

async def create_session(session_id: str) -> dict:
    """Create a new session record."""
    now = _now()
    db = await database.get_connection()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            (session_id, now, now),
        )
        await db.commit()
        return {"id": session_id, "started_at": now, "last_active": now, "memory_count": 0}
    finally:
        await db.close()


async def _update_session_activity(db, session_id: str) -> None:
    """Increment memory count and update last_active for a session. Uses existing db connection."""
    now = _now()
    # Ensure session exists (idempotent)
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
        (session_id, now, now),
    )
    await db.execute(
        "UPDATE sessions SET last_active = ?, memory_count = memory_count + 1 WHERE id = ?",
        (now, session_id),
    )


async def list_sessions(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    """List sessions with pagination, most recent first."""
    db = await database.get_connection()
    try:
        cursor = await db.execute("SELECT COUNT(*) FROM sessions")
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT * FROM sessions ORDER BY last_active DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        sessions = [dict(row) for row in await cursor.fetchall()]
        return sessions, total
    finally:
        await db.close()


async def get_session_memories(session_id: str, limit: int = 50) -> list[dict]:
    """Get all memories from a specific session."""
    db = await database.get_connection()
    try:
        cursor = await db.execute(
            "SELECT * FROM memories WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        memories = []
        for row in await cursor.fetchall():
            mem = dict(row)
            mem["tags"] = json.loads(mem["tags"])
            memories.append(mem)
        return memories
    finally:
        await db.close()


# --- Emotional Arc ---

async def get_emotional_timeline(days: int = 30, bucket: str = "day") -> list[dict]:
    """Get emotional weight over time, bucketed by day or hour."""
    db = await database.get_connection()
    try:
        if bucket == "hour":
            group_expr = "substr(created_at, 1, 13)"  # YYYY-MM-DDTHH
        else:
            group_expr = "substr(created_at, 1, 10)"  # YYYY-MM-DD

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = await db.execute(
            f"""SELECT {group_expr} as bucket,
                       AVG(emotional_weight) as avg_emotion,
                       MIN(emotional_weight) as min_emotion,
                       MAX(emotional_weight) as max_emotion,
                       COUNT(*) as count
                FROM memories
                WHERE created_at >= ?
                GROUP BY bucket
                ORDER BY bucket ASC""",
            (cutoff,),
        )
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def get_session_mood(session_id: str) -> dict:
    """Get emotional summary for a specific session."""
    db = await database.get_connection()
    try:
        cursor = await db.execute(
            """SELECT AVG(emotional_weight) as avg_emotion,
                      MIN(emotional_weight) as min_emotion,
                      MAX(emotional_weight) as max_emotion,
                      COUNT(*) as count
               FROM memories WHERE session_id = ?""",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row and row["count"] > 0:
            return {
                "avg_emotion": round(row["avg_emotion"], 3),
                "min_emotion": round(row["min_emotion"], 3),
                "max_emotion": round(row["max_emotion"], 3),
                "count": row["count"],
            }
        return {"avg_emotion": 0.0, "min_emotion": 0.0, "max_emotion": 0.0, "count": 0}
    finally:
        await db.close()


# --- Graph Data ---

async def get_graph_data(limit: int = 100) -> dict:
    """Get nodes and edges for the memory graph visualization."""
    db = await database.get_connection()
    try:
        # Get memories that have links (as nodes)
        cursor = await db.execute(
            """SELECT DISTINCT m.id, m.content, m.memory_type, m.importance,
                      m.emotional_weight, m.tags, m.created_at
               FROM memories m
               WHERE m.id IN (
                   SELECT source_memory_id FROM memory_links
                   UNION
                   SELECT target_memory_id FROM memory_links
               )
               ORDER BY m.importance DESC
               LIMIT ?""",
            (limit,),
        )
        nodes = []
        node_ids = set()
        for row in await cursor.fetchall():
            node = dict(row)
            node["tags"] = json.loads(node["tags"])
            # Truncate content for the visualization
            content = node["content"]
            node["content"] = content[:120] + "..." if len(content) > 120 else content
            nodes.append(node)
            node_ids.add(node["id"])

        # Get edges between visible nodes
        edges = []
        if node_ids:
            ph = ",".join("?" * len(node_ids))
            id_list = list(node_ids)
            cursor = await db.execute(
                f"""SELECT source_memory_id as source, target_memory_id as target,
                           link_type, strength
                    FROM memory_links
                    WHERE source_memory_id IN ({ph})
                      AND target_memory_id IN ({ph})""",
                id_list + id_list,
            )
            edges = [dict(row) for row in await cursor.fetchall()]

        return {"nodes": nodes, "edges": edges}
    finally:
        await db.close()


# --- Activation Decay (V4) ---

async def apply_activation_decay() -> dict:
    """
    Apply exponential decay to all memories' activation levels.

    Run at session startup. Memories with high importance decay slower.
    Returns stats about the decay operation.
    """
    from .decay import decay_activation

    now = _now()
    db = await database.get_connection()
    try:
        cursor = await db.execute(
            "SELECT id, importance, activation_level, last_activation_decay, created_at FROM memories"
        )
        rows = await cursor.fetchall()

        updated = 0
        for row in rows:
            last_decay = row["last_activation_decay"] or row["created_at"]
            current = row["activation_level"] if row["activation_level"] is not None else 1.0

            new_activation = decay_activation(current, row["importance"], last_decay, now)

            if new_activation != current:
                await db.execute(
                    "UPDATE memories SET activation_level = ?, last_activation_decay = ? WHERE id = ?",
                    (new_activation, now, row["id"]),
                )
                updated += 1

        await db.commit()
        return {"total": len(rows), "updated": updated, "timestamp": now}
    finally:
        await db.close()
