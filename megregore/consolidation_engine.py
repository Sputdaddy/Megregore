"""Auto-consolidation candidate detection for Megregore V5. Groups related memories for synthesis."""

import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional
from . import database
from . import embeddings

logger = logging.getLogger("megregore.consolidation_engine")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_tag_overlap(memories: list[dict]) -> float:
    """Calculate the fraction of tags shared across all memories."""
    if not memories:
        return 0.0
    tag_sets = [set(m.get("tags", [])) for m in memories]
    if not tag_sets or any(len(ts) == 0 for ts in tag_sets):
        return 0.0
    common = tag_sets[0]
    all_tags = set(tag_sets[0])
    for ts in tag_sets[1:]:
        common = common & ts
        all_tags = all_tags | ts
    return len(common) / len(all_tags) if all_tags else 0.0


def _score_candidate_group(memories: list[dict], same_thread: bool, avg_similarity: float = 0.0) -> float:
    """
    Score a group's consolidation potential (0.0-1.0).

    Pure function that evaluates how suitable a group of memories is for consolidation
    based on semantic similarity, tag overlap, thread membership, activation levels,
    group size, and importance.
    """
    if not memories:
        return 0.0

    # Extract metrics
    tag_overlap_pct = _compute_tag_overlap(memories)
    avg_activation = sum(m.get("activation_level", 1.0) for m in memories) / len(memories)
    group_size = len(memories)
    avg_importance = sum(m.get("importance", 5) for m in memories) / len(memories)

    # Weighted scoring components
    semantic_score = avg_similarity * 0.40
    tag_score = tag_overlap_pct * 0.25
    thread_score = (1.0 if same_thread else 0.0) * 0.15
    urgency_score = (1.0 - avg_activation) * 0.10

    # Optimal group size is 3-5
    if group_size <= 5:
        size_factor = 1.0 - abs(group_size - 4) * 0.25
    else:
        size_factor = max(0.0, 1.0 - (group_size - 5) * 0.15)
    size_score = max(0.0, size_factor) * 0.07

    # Moderate importance benefits most
    importance_norm = avg_importance / 10.0
    importance_score = importance_norm * 0.03

    confidence = semantic_score + tag_score + thread_score + urgency_score + size_score + importance_score
    return round(max(0.0, min(1.0, confidence)), 4)


async def _cluster_by_thread(min_size=3) -> list[dict]:
    """
    Group memories by thread membership.

    Returns list of candidate groups where memories share the same thread
    and the thread has at least min_size memories.
    """
    db = await database.get_connection()
    try:
        candidates = []

        # Find threads with enough memories
        cursor = await db.execute("""
            SELECT m.thread_id, t.title, COUNT(*) as cnt
            FROM memories m
            JOIN threads t ON m.thread_id = t.id
            WHERE m.thread_id IS NOT NULL
            GROUP BY m.thread_id
            HAVING cnt >= ?
            ORDER BY cnt DESC
        """, (min_size,))

        qualifying_threads = await cursor.fetchall()

        for row in qualifying_threads:
            thread_id, thread_title, count = row

            # Fetch memories in this thread
            mem_cursor = await db.execute("""
                SELECT id, content, importance, activation_level, tags
                FROM memories
                WHERE thread_id = ?
                ORDER BY created_at
            """, (thread_id,))

            memories = []
            memory_ids = []
            for mem_row in await mem_cursor.fetchall():
                mem_id, content, importance, activation, tags_json = mem_row
                tags = json.loads(tags_json) if tags_json else []
                memories.append({
                    "id": mem_id,
                    "content": content,
                    "importance": importance,
                    "activation_level": activation,
                    "tags": tags
                })
                memory_ids.append(mem_id)

            # Use 0.5 as reasonable default similarity for thread-grouped memories
            confidence = _score_candidate_group(memories, same_thread=True, avg_similarity=0.5)

            # Build previews
            previews = [
                {"id": m["id"], "content": m["content"][:80] + ("..." if len(m["content"]) > 80 else "")}
                for m in memories
            ]

            candidates.append({
                "memory_ids": memory_ids,
                "reason": f"Thread: '{thread_title}' ({len(memory_ids)} memories)",
                "confidence": confidence,
                "group_type": "thread",
                "previews": previews,
                "thread_id": thread_id,
                "thread_title": thread_title
            })

        return candidates

    except Exception as e:
        logger.error(f"Error clustering by thread: {e}", exc_info=True)
        return []
    finally:
        await db.close()


async def _cluster_by_similarity(threshold=0.75, min_size=3) -> list[dict]:
    """
    Find clusters of semantically similar memories using union-find.

    Returns list of candidate groups where memories are semantically similar
    above the threshold and form connected components of at least min_size.
    """
    if not await embeddings.is_available():
        logger.info("Embeddings not available, skipping similarity clustering")
        return []

    db = await database.get_connection()
    try:
        candidates = []

        # Fetch all memories
        cursor = await db.execute("""
            SELECT id, content, context, importance, activation_level, tags
            FROM memories
            ORDER BY id
        """)

        all_memories = []
        memory_map = {}
        for row in await cursor.fetchall():
            mem_id, content, context, importance, activation, tags_json = row
            tags = json.loads(tags_json) if tags_json else []
            mem_dict = {
                "id": mem_id,
                "content": content,
                "context": context,
                "importance": importance,
                "activation_level": activation,
                "tags": tags
            }
            all_memories.append(mem_dict)
            memory_map[mem_id] = mem_dict

        if len(all_memories) < min_size:
            return []

        # Build adjacency graph using semantic search
        all_ids = [m["id"] for m in all_memories]
        parent = {mid: mid for mid in all_ids}
        edges = []  # Store edges with similarity for later averaging

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b, similarity):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
                edges.append((a, b, similarity))

        # For each memory, find similar neighbors
        for mem in all_memories:
            query_text = embeddings._build_embed_text(mem["content"], mem.get("context"))
            results = await embeddings.semantic_search(query_text, limit=10)

            for neighbor_id, similarity in results:
                if neighbor_id == mem["id"]:
                    continue
                if similarity >= threshold:
                    union(mem["id"], neighbor_id, similarity)

        # Group memories by component
        components = {}
        for mid in all_ids:
            root = find(mid)
            if root not in components:
                components[root] = []
            components[root].append(mid)

        # Filter components by size and build candidates
        for root, member_ids in components.items():
            if len(member_ids) < min_size:
                continue

            # Get memory details
            memories = [memory_map[mid] for mid in member_ids]

            # Calculate average similarity for this cluster
            cluster_edges = [(a, b, sim) for a, b, sim in edges
                           if a in member_ids and b in member_ids]
            avg_similarity = sum(sim for _, _, sim in cluster_edges) / len(cluster_edges) if cluster_edges else threshold

            # Check if all in same thread
            thread_ids = set(m.get("thread_id") for m in memories if m.get("thread_id") is not None)
            same_thread = len(thread_ids) == 1

            confidence = _score_candidate_group(memories, same_thread=same_thread, avg_similarity=avg_similarity)

            # Build previews
            previews = [
                {"id": m["id"], "content": m["content"][:80] + ("..." if len(m["content"]) > 80 else "")}
                for m in memories
            ]

            candidates.append({
                "memory_ids": member_ids,
                "reason": f"Semantic cluster ({len(member_ids)} similar memories, avg similarity: {avg_similarity:.2f})",
                "confidence": confidence,
                "group_type": "similarity",
                "previews": previews
            })

        return candidates

    except Exception as e:
        logger.error(f"Error clustering by similarity: {e}", exc_info=True)
        return []
    finally:
        await db.close()


async def find_consolidation_candidates(min_group_size=3, similarity_threshold=0.75) -> list[dict]:
    """
    Main entry point. Find groups of memories that are candidates for consolidation.

    Returns a sorted list of candidate groups with the following structure:
    {
        "memory_ids": [1, 3, 5],
        "reason": "Thread: 'Megregore Development' (3 memories)",
        "confidence": 0.82,
        "group_type": "thread" | "similarity",
        "previews": [{"id": 1, "content": "first 80 chars..."}, ...]
    }

    Args:
        min_group_size: Minimum number of memories in a group (default 3)
        similarity_threshold: Minimum similarity for semantic clustering (default 0.75)
    """
    try:
        # Get thread-based groups
        thread_groups = await _cluster_by_thread(min_group_size)
        logger.info(f"Found {len(thread_groups)} thread-based candidate groups")

        # Get similarity-based groups
        similarity_groups = await _cluster_by_similarity(similarity_threshold, min_group_size)
        logger.info(f"Found {len(similarity_groups)} similarity-based candidate groups")

        # Merge and deduplicate groups
        all_groups = thread_groups + similarity_groups

        # Deduplicate: if two groups overlap significantly, keep the higher-scored one
        deduplicated = []
        used_memories = set()

        # Sort by confidence first
        all_groups.sort(key=lambda g: g["confidence"], reverse=True)

        for group in all_groups:
            group_set = set(group["memory_ids"])
            # Check if this group significantly overlaps with already-selected groups
            overlap = len(group_set & used_memories)
            overlap_pct = overlap / len(group_set) if group_set else 0

            # If less than 50% overlap, it's distinct enough to include
            if overlap_pct < 0.5:
                deduplicated.append(group)
                used_memories.update(group_set)

        # Final sort by confidence
        deduplicated.sort(key=lambda g: g["confidence"], reverse=True)

        logger.info(f"Returning {len(deduplicated)} consolidated candidate groups (after deduplication)")
        return deduplicated

    except Exception as e:
        logger.error(f"Error finding consolidation candidates: {e}", exc_info=True)
        return []
