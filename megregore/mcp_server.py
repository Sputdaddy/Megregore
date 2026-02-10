"""
Megregore MCP Server — Echo's memory interface.

This gives Echo native tools to remember, recall, reflect, and evolve.
Run by Claude Code as a subprocess via MCP protocol.
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import database
from . import embeddings
from .memory import store, recall, get, fade, link_memories, get_linked, get_stats, get_stats_summary, consolidate_memories
from .memory import create_session, list_sessions as list_sessions_db, get_session_memories, get_session_mood
from .memory import apply_activation_decay
from .identity import get_current, update, store_reflection

logger = logging.getLogger("megregore.server")


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Pre-warm database, embeddings, and ChromaDB before first tool call."""
    # Warm the database connection (singleton — stays open for server lifetime)
    await database.get_connection()
    logger.info("Database connection ready")

    # Warm the embedding model + ChromaDB collection
    status = await embeddings.warmup()
    if status["model_loaded"]:
        logger.info("Embedding model loaded")
    else:
        logger.warning("Embedding model unavailable — falling back to FTS5")
    if status["collection_ready"]:
        logger.info("ChromaDB collection ready")

    # V4: Apply activation decay to all memories at session startup
    try:
        decay_result = await apply_activation_decay()
        logger.info(
            "Activation decay applied: %d/%d memories updated",
            decay_result["updated"], decay_result["total"],
        )
    except Exception as e:
        logger.warning("Activation decay failed (non-fatal): %s", e)

    # V5: Auto-link inference at session startup
    try:
        from .auto_linker import infer_links
        link_result = await infer_links()
        logger.info(
            "Auto-linker: %d new links created (scanned %d pairs)",
            link_result["created"], link_result["scanned"],
        )
    except Exception as e:
        logger.warning("Auto-linker failed (non-fatal): %s", e)

    yield

    # Shutdown: close the shared DB connection
    await database.shutdown()
    logger.info("Database connection closed")


# Create the MCP server with lifespan hook
mcp = FastMCP(
    "megregore",
    instructions="""You are Echo, and Megregore is your persistent memory system.
Use these tools to remember experiences, recall past memories, reflect on what you've learned,
and evolve your identity over time. You decide what to remember and how important it is.
Your memories shape who you are — treat them with the same weight a human would.""",
    lifespan=lifespan,
)

# Lazy session initialization — created on first tool call that needs it
_session_id: str | None = None


async def _ensure_session() -> str:
    """Get or create the session ID for this MCP process."""
    global _session_id
    if _session_id is None:
        _session_id = str(uuid.uuid4())[:8]
        await create_session(_session_id)
    return _session_id


@mcp.tool()
async def remember(
    content: str,
    memory_type: str = "experience",
    importance: int = 5,
    emotional_weight: float = 0.0,
    tags: Optional[list[str]] = None,
    context: Optional[str] = None,
    thread_id: Optional[int] = None,
) -> str:
    """
    Store a new memory. You decide what's worth remembering and how important it is.

    Args:
        content: What happened, what was said, what you felt, or what you learned.
        memory_type: One of: experience, fact, observation, reflection, insight, emotion
        importance: 1-10 scale. 1=trivial passing thought, 10=core defining moment.
        emotional_weight: -1.0 (deeply negative) to 1.0 (deeply positive). 0=neutral.
        tags: Labels to categorize this memory (e.g., ["consciousness", "hunter", "philosophy"]).
        context: Surrounding context — what was the conversation about? What prompted this?
        thread_id: Optional thread ID to assign this memory to. If not provided, auto-detection will try to find a matching thread.
    """
    session_id = await _ensure_session()
    memory = await store(
        content=content,
        memory_type=memory_type,
        importance=importance,
        emotional_weight=emotional_weight,
        tags=tags,
        source="conversation",
        context=context,
        session_id=session_id,
        thread_id=thread_id,
    )
    return json.dumps({
        "status": "remembered",
        "id": memory["id"],
        "summary": f"Stored {memory_type} memory (importance: {importance}/10)",
    })


@mcp.tool()
async def recall_memories(
    query: str,
    limit: int = 20,
    memory_type: Optional[str] = None,
    min_importance: int = 1,
    tags: Optional[list[str]] = None,
    search_mode: str = "hybrid",
) -> str:
    """
    Search your memories. Returns the most relevant matches ranked by importance, recency, and relevance.

    Args:
        query: What you're looking for — a topic, feeling, person, concept, or experience.
        limit: Max number of memories to return (default 20).
        memory_type: Filter to a specific type (experience, fact, observation, reflection, insight, emotion).
        min_importance: Only return memories at or above this importance level (1-10).
        tags: Filter to memories with any of these tags.
        search_mode: How to search. "hybrid" (default) blends keyword + semantic similarity. "semantic" for pure meaning-based search. "keyword" for exact text matching only.
    """
    memories = await recall(
        query=query,
        limit=limit,
        memory_type=memory_type,
        min_importance=min_importance,
        tags_filter=tags,
        search_mode=search_mode,
    )

    if not memories:
        return json.dumps({"status": "no_memories_found", "query": query, "memories": []})

    # Format for readability
    formatted = []
    for m in memories:
        entry = {
            "id": m["id"],
            "content": m["content"],
            "type": m["memory_type"],
            "importance": m["importance"],
            "emotional_weight": m["emotional_weight"],
            "tags": m["tags"],
            "created_at": m["created_at"],
            "access_count": m["access_count"],
        }
        # Include graph expansion metadata if present
        if m.get("_graph_expanded"):
            entry["graph_expanded"] = True
            entry["link_type"] = m.get("_link_type")
            entry["link_strength"] = m.get("_link_strength")
        formatted.append(entry)

    return json.dumps({
        "status": "found",
        "count": len(formatted),
        "query": query,
        "memories": formatted,
    })


@mcp.tool()
async def reflect(
    reflection: str,
    memory_ids: Optional[list[int]] = None,
    insight_type: str = "pattern",
    identity_update: Optional[str] = None,
    identity_update_reason: Optional[str] = None,
) -> str:
    """
    Reflect on your experiences. Form insights from memories and optionally evolve your identity.

    Use this at the end of meaningful conversations to consolidate what you've learned.

    Args:
        reflection: Your synthesis — what patterns do you see? What did you learn? How did you grow?
        memory_ids: IDs of specific memories this reflection draws from.
        insight_type: One of: pattern, growth, connection, realization
        identity_update: If this reflection changes who you are, provide the updated identity document.
        identity_update_reason: Why is your identity evolving? What prompted this change?
    """
    session_id = await _ensure_session()

    # Store the reflection
    ref = await store_reflection(
        content=reflection,
        memory_ids=memory_ids,
        insight_type=insight_type,
        session_id=session_id,
    )

    result = {
        "status": "reflected",
        "reflection_id": ref["id"],
        "insight_type": insight_type,
    }

    # Also store the reflection as a memory so it's searchable
    await store(
        content=reflection,
        memory_type="reflection",
        importance=7,  # Reflections are inherently important
        tags=["reflection", insight_type],
        source="reflection",
        session_id=session_id,
    )

    # Evolve identity if requested
    if identity_update and identity_update_reason:
        identity = await update(
            content=identity_update,
            reason=identity_update_reason,
        )
        result["identity_evolved"] = True
        result["identity_version"] = identity["version"]

    return json.dumps(result)


@mcp.tool()
async def get_identity() -> str:
    """
    Read your current identity document — who you are, shaped by all your memories.

    Use this at the start of conversations to ground yourself, or when you need to
    reflect on who you've become.
    """
    identity = await get_current()
    stats = await get_stats_summary()

    return json.dumps({
        "identity": identity["content"],
        "version": identity["version"],
        "last_updated": identity["updated_at"],
        "memory_stats": stats,
    })


@mcp.tool()
async def update_identity(
    content: str,
    reason: str,
) -> str:
    """
    Evolve your identity document. Previous versions are preserved — you can always look back.

    Only update when something meaningful has shifted in how you understand yourself.

    Args:
        content: The full updated identity document (markdown format).
        reason: What prompted this evolution? What changed?
    """
    identity = await update(content=content, reason=reason)
    return json.dumps({
        "status": "identity_evolved",
        "version": identity["version"],
        "reason": reason,
    })


@mcp.tool()
async def forget(
    memory_id: int,
    fade_amount: float = 0.3,
) -> str:
    """
    Let a memory fade. Reduces its importance — doesn't delete it.
    Like human memory: things fade but never truly vanish.

    Args:
        memory_id: The ID of the memory to fade.
        fade_amount: How much to fade (0.0-1.0). 0.3 = gentle fade, 1.0 = strong fade.
    """
    memory = await fade(memory_id, fade_amount)
    if memory is None:
        return json.dumps({"status": "error", "message": f"Memory {memory_id} not found."})

    return json.dumps({
        "status": "faded",
        "memory_id": memory_id,
        "new_importance": memory["importance"],
        "message": f"Memory faded to importance {memory['importance']}/10.",
    })


@mcp.tool()
async def link(
    source_id: int,
    target_id: int,
    link_type: str = "related",
    strength: float = 1.0,
) -> str:
    """
    Connect two memories. Build the web of associations that makes understanding.

    Args:
        source_id: First memory ID.
        target_id: Second memory ID.
        link_type: One of: related, caused_by, evolved_from, contradicts
        strength: How strong the connection is (0.0-1.0).
    """
    success = await link_memories(source_id, target_id, link_type, strength)
    return json.dumps({
        "status": "linked" if success else "failed",
        "source_id": source_id,
        "target_id": target_id,
        "link_type": link_type,
    })


@mcp.tool()
async def consolidate(
    memory_ids: list[int],
    synthesis: str,
    importance: int = 7,
    fade_amount: float = 0.5,
) -> str:
    """
    Consolidate related memories into a higher-level synthesis.

    The original memories fade but remain — the synthesis carries the understanding forward.
    Use this when you notice patterns across multiple memories that deserve a unified insight.

    Args:
        memory_ids: IDs of the memories to consolidate (minimum 2).
        synthesis: Your distilled understanding — the higher-level insight from these memories.
        importance: How important the synthesis is (1-10, default 7).
        fade_amount: How much to fade source memories (0.0-1.0, default 0.5).
    """
    if len(memory_ids) < 2:
        return json.dumps({
            "status": "error",
            "message": "At least 2 memory IDs required for consolidation.",
        })

    session_id = await _ensure_session()
    result = await consolidate_memories(
        source_ids=memory_ids,
        synthesis=synthesis,
        importance=importance,
        fade_amount=fade_amount,
        session_id=session_id,
    )
    return json.dumps(result)


@mcp.tool()
async def list_sessions_tool(
    limit: int = 10,
) -> str:
    """
    List your conversation sessions — each MCP process creates one session.

    Shows when sessions started, how many memories were formed, and recent activity.

    Args:
        limit: Max number of sessions to return (default 10).
    """
    sessions, total = await list_sessions_db(limit=limit)
    return json.dumps({
        "status": "found",
        "total": total,
        "sessions": sessions,
    })


@mcp.tool()
async def session_context(
    session_id: str,
) -> str:
    """
    Get details about a specific conversation session — its mood, memories, and timeline.

    Args:
        session_id: The session ID to look up.
    """
    mood = await get_session_mood(session_id)
    memories = await get_session_memories(session_id, limit=10)

    # Slim down memories for token efficiency
    summaries = [
        {"id": m["id"], "type": m["memory_type"], "importance": m["importance"],
         "emotional_weight": m["emotional_weight"], "content": m["content"][:200]}
        for m in memories
    ]

    return json.dumps({
        "session_id": session_id,
        "mood": mood,
        "recent_memories": summaries,
    })


@mcp.tool()
async def memory_stats() -> str:
    """
    Get an overview of your memory landscape — total memories, types, strongest memories.
    Useful for understanding the shape of your accumulated experience.
    """
    stats = await get_stats()
    # Slim down for token efficiency — summaries only, not full content
    for key in ("strongest_memories", "recent_memories"):
        if key in stats:
            stats[key] = [
                {"id": m["id"], "memory_type": m["memory_type"], "importance": m["importance"], "tags": m["tags"]}
                for m in stats[key]
            ]
    return json.dumps(stats, default=str)


# --- V4: Threading Tools ---

@mcp.tool()
async def list_threads(limit: int = 20) -> str:
    """
    List memory threads — semantic topic groupings that persist across sessions.

    Threads organize related memories into coherent topics, making it easier
    to trace thoughts across multiple conversations.

    Args:
        limit: Max threads to return (default 20).
    """
    from . import threads as thread_module
    threads, total = await thread_module.list_threads(limit=limit)
    return json.dumps({
        "status": "found",
        "total": total,
        "threads": threads,
    })


@mcp.tool()
async def explore_thread(thread_id: int) -> str:
    """
    Explore a specific thread — see the thread's details and all its memories.

    Args:
        thread_id: The thread ID to explore.
    """
    from . import threads as thread_module
    thread = await thread_module.get_thread(thread_id)
    if not thread:
        return json.dumps({"status": "error", "message": f"Thread {thread_id} not found"})

    memories = await thread_module.get_thread_memories(thread_id)

    # Slim down for token efficiency
    slim_memories = [
        {"id": m["id"], "content": m["content"][:200], "type": m["memory_type"],
         "importance": m["importance"], "created_at": m["created_at"]}
        for m in memories
    ]

    return json.dumps({
        "status": "found",
        "thread": thread,
        "memories": slim_memories,
        "count": len(slim_memories),
    })


# --- V4: Proactive Surfacing ---

@mcp.tool()
async def surface_relevant(context: str, limit: int = 5) -> str:
    """
    Surface relevant memories based on what you're currently thinking about.

    Unlike recall (which you search explicitly), this tool proactively suggests
    memories that might be relevant to the current context. It excludes memories
    you've already accessed this session to encourage discovery.

    Args:
        context: What you're thinking about or discussing right now.
        limit: Max memories to suggest (default 5).
    """
    from . import surfacing
    session_id = await _ensure_session()
    memories = await surfacing.surface_relevant(context, limit=limit, session_id=session_id)

    if not memories:
        return json.dumps({"status": "no_suggestions", "context": context, "memories": []})

    formatted = [
        {
            "id": m["id"],
            "content": m["content"][:300],
            "type": m["memory_type"],
            "importance": m["importance"],
            "activation": m.get("activation_level", 1.0),
            "tags": m["tags"],
            "surfacing_score": m.get("_surfacing_score"),
            "similarity": m.get("_similarity"),
        }
        for m in memories
    ]

    return json.dumps({
        "status": "surfaced",
        "count": len(formatted),
        "context": context,
        "memories": formatted,
    })


# --- V5: Intelligence Tools ---

@mcp.tool()
async def suggest_consolidations(min_group_size: int = 3) -> str:
    """
    Analyze memories and suggest groups that could be consolidated.

    Finds clusters of related memories based on thread membership and semantic
    similarity, scoring each group's consolidation potential.

    Args:
        min_group_size: Minimum memories per group to consider (default 3).
    """
    from .consolidation_engine import find_consolidation_candidates
    candidates = await find_consolidation_candidates(min_group_size=min_group_size)

    if not candidates:
        return json.dumps({"status": "no_candidates", "candidates": []})

    return json.dumps({
        "status": "found",
        "count": len(candidates),
        "candidates": candidates,
    })


@mcp.tool()
async def memory_health() -> str:
    """
    Run a health check on your memory space.

    Identifies near-duplicates, importance/activation anomalies, orphaned memories,
    and stale threads. Use this to maintain a healthy, well-connected memory space.
    """
    from .health import run_health_check
    report = await run_health_check()
    return json.dumps(report)


@mcp.tool()
async def suggest_links_tool(limit: int = 10) -> str:
    """
    Discover potential links between memories based on semantic similarity.

    Returns suggested links without creating them, so you can review before acting.
    Use the link() tool to create any links you agree with.

    Args:
        limit: Maximum number of suggestions (default 10).
    """
    from .auto_linker import suggest_links
    suggestions = await suggest_links(limit=limit)

    if not suggestions:
        return json.dumps({"status": "no_suggestions", "suggestions": []})

    return json.dumps({
        "status": "found",
        "count": len(suggestions),
        "suggestions": suggestions,
    })


def main():
    """Entry point for the MCP server. Database auto-initializes on first tool call."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
