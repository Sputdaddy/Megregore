"""Socratic Dialogue Engine for Megregore. Tracks philosophical beliefs, arguments, tensions, and evolution."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database

logger = logging.getLogger("megregore.beliefs")

# Separate ChromaDB collection for belief-to-belief semantic matching
_beliefs_collection = None
_beliefs_collection_lock = asyncio.Lock()

VALID_DOMAINS = {"consciousness", "metaphysics", "quantum", "epistemology", "ethics", "identity", "simulation", "general"}
VALID_STATUSES = {"active", "revised", "abandoned", "exploring"}
VALID_ARGUMENT_TYPES = {"supporting", "counter", "qualifier"}
VALID_TENSION_TYPES = {"contradiction", "tension", "dependency", "refinement"}
VALID_TENSION_STATUSES = {"unresolved", "explored", "resolved", "accepted"}
VALID_LINK_TYPES = {"evidence", "origin", "context", "counterpoint"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_beliefs_collection():
    """Get or create the beliefs ChromaDB collection (separate from memories)."""
    global _beliefs_collection

    if _beliefs_collection is not None:
        return _beliefs_collection

    async with _beliefs_collection_lock:
        if _beliefs_collection is not None:
            return _beliefs_collection
        try:
            from .embeddings import _chroma_client, _ensure_model
            if not await _ensure_model():
                return None
            if _chroma_client is None:
                # Try to init via warmup
                from .embeddings import _ensure_collection
                await _ensure_collection()
                from .embeddings import _chroma_client as client
                if client is None:
                    return None
            else:
                client = _chroma_client

            loop = asyncio.get_running_loop()
            _beliefs_collection = await loop.run_in_executor(
                None,
                lambda: client.get_or_create_collection(
                    name="megregore_beliefs",
                    metadata={"hnsw:space": "cosine"},
                ),
            )
            logger.info("Beliefs ChromaDB collection ready")
            return _beliefs_collection
        except Exception as e:
            logger.warning("Beliefs ChromaDB unavailable: %s", e)
            return None


async def _embed_belief(belief_id: int, content: str) -> bool:
    """Embed a belief in the beliefs ChromaDB collection."""
    try:
        from .embeddings import _ensure_model, _model
        if not await _ensure_model():
            return False
        collection = await _get_beliefs_collection()
        if collection is None:
            return False

        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(
            None, lambda: _model.encode(content).tolist()
        )
        await loop.run_in_executor(
            None,
            lambda: collection.upsert(
                ids=[str(belief_id)],
                embeddings=[embedding],
                documents=[content],
            ),
        )
        return True
    except Exception as e:
        logger.warning("Failed to embed belief %d: %s", belief_id, e)
        return False


async def _search_similar_beliefs(query: str, limit: int = 10) -> list[tuple[int, float]]:
    """Search for semantically similar beliefs. Returns (belief_id, similarity) pairs."""
    try:
        from .embeddings import _ensure_model, _model
        if not await _ensure_model():
            return []
        collection = await _get_beliefs_collection()
        if collection is None:
            return []

        loop = asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(
            None, lambda: _model.encode(query).tolist()
        )
        results = await loop.run_in_executor(
            None,
            lambda: collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                include=["distances"],
            ),
        )
        if not results["ids"] or not results["ids"][0]:
            return []

        pairs = []
        for id_str, distance in zip(results["ids"][0], results["distances"][0]):
            similarity = 1.0 - (distance / 2.0)
            pairs.append((int(id_str), similarity))
        return pairs
    except Exception as e:
        logger.warning("Belief semantic search failed: %s", e)
        return []


# --- CRUD Operations ---


async def record_belief(content: str, domain: str = "general", confidence: float = 0.5,
                        source_context: Optional[str] = None, session_id: Optional[str] = None) -> dict:
    """Create a new belief."""
    db = await database.get_connection()
    now = _now()
    cursor = await db.execute(
        """INSERT INTO beliefs (content, domain, confidence, status, source_context, session_id, created_at, updated_at)
        VALUES (?, ?, ?, 'active', ?, ?, ?, ?)""",
        (content, domain, confidence, source_context, session_id, now, now),
    )
    belief_id = cursor.lastrowid
    await db.commit()

    # Embed asynchronously (non-blocking, best-effort)
    await _embed_belief(belief_id, content)

    cursor = await db.execute("SELECT * FROM beliefs WHERE id = ?", (belief_id,))
    row = await cursor.fetchone()
    return dict(row)


async def update_belief(belief_id: int, content: Optional[str] = None, confidence: Optional[float] = None,
                        status: Optional[str] = None, change_reason: str = "Updated",
                        session_id: Optional[str] = None) -> Optional[dict]:
    """Update belief after saving current state to evolution history."""
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT content, confidence, status FROM beliefs WHERE id = ?", (belief_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    current = dict(row)

    now = _now()
    # Save evolution history
    await db.execute(
        """INSERT INTO belief_evolution
        (belief_id, previous_content, previous_confidence, previous_status, change_reason, session_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (belief_id, current["content"], current["confidence"], current["status"],
         change_reason, session_id, now),
    )

    # Build dynamic update
    updates = ["updated_at = ?"]
    params = [now]
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if confidence is not None:
        updates.append("confidence = ?")
        params.append(confidence)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    params.append(belief_id)

    await db.execute(f"UPDATE beliefs SET {', '.join(updates)} WHERE id = ?", params)
    await db.commit()

    # Re-embed if content changed
    if content is not None:
        await _embed_belief(belief_id, content)

    cursor = await db.execute("SELECT * FROM beliefs WHERE id = ?", (belief_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_belief(belief_id: int) -> Optional[dict]:
    """Get belief with arguments, tensions, linked memories, and evolution."""
    db = await database.get_connection()

    cursor = await db.execute("SELECT * FROM beliefs WHERE id = ?", (belief_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    belief = dict(row)

    cursor = await db.execute(
        "SELECT * FROM belief_arguments WHERE belief_id = ? ORDER BY created_at", (belief_id,)
    )
    arguments = [dict(r) for r in await cursor.fetchall()]

    cursor = await db.execute(
        """SELECT bt.*, b1.content as belief_a_content, b2.content as belief_b_content
        FROM belief_tensions bt
        JOIN beliefs b1 ON bt.belief_a_id = b1.id
        JOIN beliefs b2 ON bt.belief_b_id = b2.id
        WHERE bt.belief_a_id = ? OR bt.belief_b_id = ?
        ORDER BY bt.severity DESC""",
        (belief_id, belief_id),
    )
    tensions = [dict(r) for r in await cursor.fetchall()]

    cursor = await db.execute(
        """SELECT bml.*, m.content as memory_content, m.memory_type, m.importance
        FROM belief_memory_links bml
        JOIN memories m ON bml.memory_id = m.id
        WHERE bml.belief_id = ?
        ORDER BY bml.created_at""",
        (belief_id,),
    )
    linked_memories = [dict(r) for r in await cursor.fetchall()]

    cursor = await db.execute(
        "SELECT * FROM belief_evolution WHERE belief_id = ? ORDER BY id DESC",
        (belief_id,),
    )
    evolution = [dict(r) for r in await cursor.fetchall()]

    return {
        "belief": belief,
        "arguments": arguments,
        "tensions": tensions,
        "linked_memories": linked_memories,
        "evolution": evolution,
    }


async def add_argument(belief_id: int, content: str, argument_type: str = "supporting",
                       strength: float = 0.5, source_memory_id: Optional[int] = None,
                       session_id: Optional[str] = None) -> dict:
    """Add an argument to a belief."""
    db = await database.get_connection()
    now = _now()
    cursor = await db.execute(
        """INSERT INTO belief_arguments
        (belief_id, content, argument_type, strength, source_memory_id, session_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (belief_id, content, argument_type, strength, source_memory_id, session_id, now),
    )
    arg_id = cursor.lastrowid
    await db.commit()

    cursor = await db.execute("SELECT * FROM belief_arguments WHERE id = ?", (arg_id,))
    row = await cursor.fetchone()
    return dict(row)


async def record_tension(belief_a_id: int, belief_b_id: int, tension_type: str = "contradiction",
                         description: str = "", severity: float = 0.5,
                         detection_method: str = "manual", session_id: Optional[str] = None) -> dict:
    """Record a tension between two beliefs. Returns existing if duplicate."""
    db = await database.get_connection()
    now = _now()

    try:
        cursor = await db.execute(
            """INSERT INTO belief_tensions
            (belief_a_id, belief_b_id, tension_type, description, severity, status, detection_method, session_id, created_at)
            VALUES (?, ?, ?, ?, ?, 'unresolved', ?, ?, ?)""",
            (belief_a_id, belief_b_id, tension_type, description, severity, detection_method, session_id, now),
        )
        tension_id = cursor.lastrowid
        await db.commit()
    except Exception as e:
        if "UNIQUE" in str(e):
            cursor = await db.execute(
                """SELECT * FROM belief_tensions
                WHERE belief_a_id = ? AND belief_b_id = ? AND tension_type = ?""",
                (belief_a_id, belief_b_id, tension_type),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
        raise

    cursor = await db.execute("SELECT * FROM belief_tensions WHERE id = ?", (tension_id,))
    row = await cursor.fetchone()
    return dict(row)


async def link_belief_to_memory(belief_id: int, memory_id: int, link_type: str = "evidence") -> dict:
    """Link a belief to a memory. Returns existing if duplicate."""
    db = await database.get_connection()
    now = _now()

    try:
        cursor = await db.execute(
            """INSERT INTO belief_memory_links (belief_id, memory_id, link_type, created_at)
            VALUES (?, ?, ?, ?)""",
            (belief_id, memory_id, link_type, now),
        )
        link_id = cursor.lastrowid
        await db.commit()
    except Exception as e:
        if "UNIQUE" in str(e):
            cursor = await db.execute(
                """SELECT * FROM belief_memory_links
                WHERE belief_id = ? AND memory_id = ? AND link_type = ?""",
                (belief_id, memory_id, link_type),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
        raise

    cursor = await db.execute("SELECT * FROM belief_memory_links WHERE id = ?", (link_id,))
    row = await cursor.fetchone()
    return dict(row)


# --- Query Operations ---


async def list_beliefs(domain: Optional[str] = None, status: Optional[str] = None,
                       min_confidence: Optional[float] = None, limit: int = 50,
                       offset: int = 0) -> tuple[list[dict], int]:
    """List beliefs with filters and pagination."""
    db = await database.get_connection()

    conditions = []
    params = []
    if domain:
        conditions.append("b.domain = ?")
        params.append(domain)
    if status:
        conditions.append("b.status = ?")
        params.append(status)
    if min_confidence is not None:
        conditions.append("b.confidence >= ?")
        params.append(min_confidence)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor = await db.execute(f"SELECT COUNT(*) FROM beliefs b {where}", params)
    total = (await cursor.fetchone())[0]

    cursor = await db.execute(
        f"""SELECT b.*,
            (SELECT COUNT(*) FROM belief_arguments WHERE belief_id = b.id) as argument_count,
            (SELECT COUNT(*) FROM belief_tensions WHERE belief_a_id = b.id OR belief_b_id = b.id) as tension_count
        FROM beliefs b {where}
        ORDER BY b.updated_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    beliefs = [dict(r) for r in await cursor.fetchall()]
    return beliefs, total


async def get_belief_graph_data() -> dict:
    """Return D3-compatible graph data."""
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT id, content, domain, confidence, status FROM beliefs WHERE status != 'abandoned'"
    )
    nodes = []
    for row in await cursor.fetchall():
        r = dict(row)
        r["content"] = r["content"][:80] + ("..." if len(r["content"]) > 80 else "")
        nodes.append(r)

    cursor = await db.execute(
        "SELECT belief_a_id as source, belief_b_id as target, tension_type, severity, status FROM belief_tensions"
    )
    edges = [dict(r) for r in await cursor.fetchall()]

    return {"nodes": nodes, "edges": edges}


async def get_domain_stats() -> list[dict]:
    """Get statistics for all domains with beliefs."""
    db = await database.get_connection()
    cursor = await db.execute(
        """SELECT domain, COUNT(*) as count, ROUND(AVG(confidence), 3) as avg_confidence
        FROM beliefs GROUP BY domain ORDER BY count DESC"""
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_domain_summary(domain: str) -> dict:
    """Get detailed summary for a domain."""
    db = await database.get_connection()

    cursor = await db.execute(
        """SELECT COUNT(*) as beliefs_count, ROUND(AVG(confidence), 3) as avg_confidence,
            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_count
        FROM beliefs WHERE domain = ?""",
        (domain,),
    )
    row = await cursor.fetchone()
    if not row or row["beliefs_count"] == 0:
        return {"domain": domain, "beliefs_count": 0}
    stats = dict(row)

    cursor = await db.execute(
        """SELECT COUNT(*) as tensions_count FROM belief_tensions bt
        JOIN beliefs b1 ON bt.belief_a_id = b1.id
        JOIN beliefs b2 ON bt.belief_b_id = b2.id
        WHERE b1.domain = ? OR b2.domain = ?""",
        (domain, domain),
    )
    stats["tensions_count"] = (await cursor.fetchone())["tensions_count"]

    cursor = await db.execute(
        """SELECT id, content, confidence, status FROM beliefs
        WHERE domain = ? ORDER BY confidence DESC LIMIT 5""",
        (domain,),
    )
    stats["top_beliefs"] = [dict(r) for r in await cursor.fetchall()]
    stats["domain"] = domain
    return stats


async def get_belief_evolution(belief_id: int) -> list[dict]:
    """Get evolution history for a belief."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM belief_evolution WHERE belief_id = ? ORDER BY id DESC",
        (belief_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_belief_arguments(belief_id: int) -> list[dict]:
    """Get all arguments for a belief."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM belief_arguments WHERE belief_id = ? ORDER BY created_at",
        (belief_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_all_tensions(status_filter: Optional[str] = None) -> list[dict]:
    """Get all tensions with belief content, optionally filtered by status."""
    db = await database.get_connection()

    query = """SELECT bt.*, b1.content as belief_a_content, b2.content as belief_b_content
        FROM belief_tensions bt
        JOIN beliefs b1 ON bt.belief_a_id = b1.id
        JOIN beliefs b2 ON bt.belief_b_id = b2.id"""
    params = []
    if status_filter:
        query += " WHERE bt.status = ?"
        params.append(status_filter)
    query += " ORDER BY bt.severity DESC"

    cursor = await db.execute(query, params)
    return [dict(r) for r in await cursor.fetchall()]


# --- The Key Function ---


async def get_philosophical_context(topic: str, limit: int = 10) -> dict:
    """Get rich philosophical context for a topic. Echo calls this before engaging in dialogue.

    Returns relevant beliefs, tensions, related memories, and question seeds.
    """
    db = await database.get_connection()

    # 1. Find beliefs matching the topic via keyword search
    keyword_beliefs = []
    cursor = await db.execute(
        """SELECT b.*,
            (SELECT COUNT(*) FROM belief_arguments WHERE belief_id = b.id) as argument_count,
            (SELECT COUNT(*) FROM belief_arguments WHERE belief_id = b.id AND argument_type = 'counter') as counter_count
        FROM beliefs b
        WHERE b.content LIKE ? AND b.status != 'abandoned'
        ORDER BY b.confidence DESC LIMIT ?""",
        (f"%{topic}%", limit),
    )
    keyword_beliefs = [dict(r) for r in await cursor.fetchall()]
    found_ids = {b["id"] for b in keyword_beliefs}

    # 2. Find semantically similar beliefs via ChromaDB
    semantic_beliefs = []
    similar = await _search_similar_beliefs(topic, limit=limit)
    if similar:
        for belief_id, similarity in similar:
            if belief_id not in found_ids and similarity > 0.6:
                cursor = await db.execute(
                    """SELECT b.*,
                        (SELECT COUNT(*) FROM belief_arguments WHERE belief_id = b.id) as argument_count,
                        (SELECT COUNT(*) FROM belief_arguments WHERE belief_id = b.id AND argument_type = 'counter') as counter_count
                    FROM beliefs b WHERE b.id = ? AND b.status != 'abandoned'""",
                    (belief_id,),
                )
                row = await cursor.fetchone()
                if row:
                    entry = dict(row)
                    entry["_similarity"] = round(similarity, 3)
                    semantic_beliefs.append(entry)
                    found_ids.add(belief_id)

    all_beliefs = keyword_beliefs + semantic_beliefs

    # 3. Find tensions involving these beliefs
    tensions = []
    if found_ids:
        placeholders = ",".join("?" * len(found_ids))
        ids_list = list(found_ids)
        cursor = await db.execute(
            f"""SELECT bt.*, b1.content as belief_a_content, b2.content as belief_b_content
            FROM belief_tensions bt
            JOIN beliefs b1 ON bt.belief_a_id = b1.id
            JOIN beliefs b2 ON bt.belief_b_id = b2.id
            WHERE bt.belief_a_id IN ({placeholders}) OR bt.belief_b_id IN ({placeholders})
            ORDER BY bt.severity DESC""",
            ids_list + ids_list,
        )
        tensions = [dict(r) for r in await cursor.fetchall()]

    # 4. Find related memories via belief_memory_links
    related_memories = []
    if found_ids:
        placeholders = ",".join("?" * len(found_ids))
        ids_list = list(found_ids)
        cursor = await db.execute(
            f"""SELECT m.id, m.content, m.memory_type, m.importance, m.emotional_weight,
                bml.link_type, bml.belief_id
            FROM belief_memory_links bml
            JOIN memories m ON bml.memory_id = m.id
            WHERE bml.belief_id IN ({placeholders})
            ORDER BY m.importance DESC LIMIT 20""",
            ids_list,
        )
        related_memories = [dict(r) for r in await cursor.fetchall()]

    # 5. Generate question seeds based on the tension landscape
    question_seeds = _generate_question_seeds(all_beliefs, tensions)

    return {
        "topic": topic,
        "beliefs": all_beliefs,
        "belief_count": len(all_beliefs),
        "tensions": tensions,
        "tension_count": len(tensions),
        "related_memories": related_memories,
        "question_seeds": question_seeds,
    }


def _generate_question_seeds(beliefs: list[dict], tensions: list[dict]) -> list[str]:
    """Generate Socratic question seeds based on beliefs and tensions."""
    seeds = []

    # Questions from unresolved tensions
    for t in tensions:
        if t.get("status") == "unresolved":
            if t["tension_type"] == "contradiction":
                seeds.append(
                    f"You believe '{t['belief_a_content'][:60]}...' but also '{t['belief_b_content'][:60]}...' — how do you reconcile these?"
                )
            elif t["tension_type"] == "tension":
                seeds.append(
                    f"There's tension between your views on '{t['belief_a_content'][:40]}...' and '{t['belief_b_content'][:40]}...' — which pulls stronger?"
                )

    # Questions from beliefs lacking counter-arguments
    for b in beliefs:
        if b.get("counter_count", 0) == 0 and b.get("argument_count", 0) > 0:
            seeds.append(
                f"What's the strongest argument against '{b['content'][:60]}...'?"
            )

    # Questions from low-confidence beliefs
    for b in beliefs:
        if b["confidence"] < 0.3 and b["status"] == "active":
            seeds.append(
                f"Your confidence in '{b['content'][:60]}...' is low ({b['confidence']:.0%}) — what would move it higher?"
            )

    # Questions from high-confidence beliefs (challenge certainty)
    for b in beliefs:
        if b["confidence"] > 0.9 and b["status"] == "active":
            seeds.append(
                f"You're very confident ({b['confidence']:.0%}) that '{b['content'][:60]}...' — what could change your mind?"
            )

    # Questions about exploring beliefs
    for b in beliefs:
        if b["status"] == "exploring":
            seeds.append(
                f"You're exploring '{b['content'][:60]}...' — what evidence would you need to commit?"
            )

    return seeds[:10]  # Cap at 10 seeds
