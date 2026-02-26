"""
Megregore MCP Server — Echo's memory interface.

This gives Echo native tools to remember, recall, reflect, and evolve.
Run by Claude Code as a subprocess via MCP protocol.
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import database
from . import embeddings
from .memory import store, recall, get, fade, link_memories, get_linked, get_stats, get_stats_summary, consolidate_memories
from .memory import create_session, list_sessions as list_sessions_db, get_session_memories, get_session_mood
from .memory import apply_activation_decay
from .identity import get_current, update, store_reflection

# V8: Self-awareness modules
from .growth import compute_growth_snapshot, get_growth_trajectory, check_contradiction_resolutions, should_generate_snapshot
from .introspection_budget import is_self_referential, update_budget, get_budget, get_budget_history, get_budget_message, record_tool_call, is_deliberate_session
from .blind_spots import run_blind_spot_scan, should_run_scan
from .alignment import compute_alignment, get_alignment_history
from .self_model import (
    make_prediction, evaluate_pending_predictions,
    get_prediction_accuracy, get_surprising_outcomes, generate_behavioral_prediction,
)

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

    # V8: Evaluate pending self-model predictions
    try:
        pred_result = await evaluate_pending_predictions()
        if pred_result["evaluated"] > 0:
            logger.info(
                "Self-model: %d predictions evaluated (verified=%d, falsified=%d)",
                pred_result["evaluated"], pred_result["verified"], pred_result["falsified"],
            )
    except Exception as e:
        logger.warning("Prediction evaluation failed (non-fatal): %s", e)

    # V8: Blind spot scan if stale (>7 days)
    try:
        if await should_run_scan():
            scan = await run_blind_spot_scan()
            logger.info("Blind spot scan: coverage=%.4f", scan["coverage_score"])
    except Exception as e:
        logger.warning("Blind spot scan failed (non-fatal): %s", e)

    # V8: Growth snapshot if stale (>3 days)
    try:
        if await should_generate_snapshot():
            snap = await compute_growth_snapshot()
            logger.info("Growth snapshot: integration=%.4f", snap["integration_score"])
    except Exception as e:
        logger.warning("Growth snapshot failed (non-fatal): %s", e)

    yield

    # Shutdown: close the shared DB connection
    await database.shutdown()
    logger.info("Database connection closed")


# Create the MCP server with lifespan hook
mcp = FastMCP(
    "megregore",
    instructions="Echo's persistent memory, identity, and belief system.",
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
async def session_start() -> str:
    """
    Initialize a session. Returns identity, temporal context, recent/important memories,
    and last session summary in a single call. Use at conversation start.
    """
    session_id = await _ensure_session()
    from .session_startup import build_session_start
    result = await build_session_start(session_id)
    return json.dumps(result)


@mcp.tool()
async def remember(
    content: str,
    memory_type: str = "experience",
    importance: int = 5,
    emotional_weight: float = 0.0,
    tags: Optional[list[str]] = None,
    context: Optional[str] = None,
    thread_id: Optional[int] = None,
    is_permanent: bool = False,
) -> str:
    """
    Store a new memory.

    Args:
        content: What happened, what was said, what you felt, or what you learned.
        memory_type: One of: experience, fact, observation, reflection, insight, emotion, procedure
        importance: 1-10 scale. 1=trivial, 10=core defining moment.
        emotional_weight: -1.0 (negative) to 1.0 (positive). 0=neutral.
        tags: Categorization labels (e.g., ["consciousness", "hunter"]).
        context: What prompted this memory?
        thread_id: Thread ID to assign to. Auto-detected if omitted.
        is_permanent: If true, memory is always loaded at session start and exempt from decay.
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
        is_permanent=is_permanent,
    )

    # V8: Classify self-referential and update introspection budget
    self_ref = is_self_referential(content, memory_type)
    if self_ref:
        db = await database.get_connection()
        await db.execute(
            "UPDATE memories SET is_self_referential = 1 WHERE id = ?",
            (memory["id"],),
        )
        await db.commit()

    budget = await update_budget(session_id)
    deliberate = is_deliberate_session(session_id)
    budget_msg = get_budget_message(budget["status"], budget["ratio"], deliberate=deliberate)

    result = {
        "status": "remembered",
        "id": memory["id"],
        "summary": f"Stored {memory_type} memory (importance: {importance}/10)",
    }
    if budget_msg:
        result["introspection_note"] = budget_msg

    return json.dumps(result)


@mcp.tool()
async def recall_memories(
    query: str,
    limit: int = 20,
    memory_type: Optional[str] = None,
    min_importance: int = 1,
    tags: Optional[list[str]] = None,
    search_mode: str = "hybrid",
    content_length: str = "summary",
    expand_graph: bool = False,
) -> str:
    """
    Search memories ranked by relevance.

    Args:
        query: What you're looking for — a topic, feeling, person, concept, or experience.
        limit: Max memories to return (default 20).
        memory_type: Filter by type (experience, fact, observation, reflection, insight, emotion).
        min_importance: Minimum importance level (1-10).
        tags: Filter to memories with any of these tags.
        search_mode: "hybrid" (default), "semantic", or "keyword".
        content_length: "full" (no truncation), "summary" (300 chars, default), or "brief" (150 chars).
        expand_graph: Include linked neighbor memories (default False).
    """
    session_id = await _ensure_session()
    memories = await recall(
        query=query,
        limit=limit,
        memory_type=memory_type,
        min_importance=min_importance,
        tags_filter=tags,
        search_mode=search_mode,
        session_id=session_id,
        expand_graph=expand_graph,
    )

    if not memories:
        return json.dumps({"status": "no_memories_found", "query": query, "memories": []})

    # Determine truncation limit
    max_len = {"full": None, "summary": 300, "brief": 150}.get(content_length)

    # Format for readability
    formatted = []
    for m in memories:
        content = m["content"]
        entry = {
            "id": m["id"],
            "type": m["memory_type"],
            "importance": m["importance"],
            "emotional_weight": m["emotional_weight"],
            "tags": m["tags"],
            "created_at": m["created_at"],
            "access_count": m["access_count"],
        }
        if max_len and len(content) > max_len:
            entry["content"] = content[:max_len] + "..."
            entry["has_more"] = True
        else:
            entry["content"] = content
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
    Form insights from memories and optionally evolve identity.

    Args:
        reflection: Your synthesis — patterns, learnings, growth.
        memory_ids: IDs of memories this reflection draws from.
        insight_type: One of: pattern, growth, connection, realization
        identity_update: Updated identity document (markdown), if changed.
        identity_update_reason: Why identity is evolving.
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

    # V8: Check introspection budget
    budget = await update_budget(session_id)
    deliberate = is_deliberate_session(session_id)
    budget_msg = get_budget_message(budget["status"], budget["ratio"], deliberate=deliberate)
    if budget_msg:
        result["introspection_note"] = budget_msg

    return json.dumps(result)


@mcp.tool()
async def get_identity() -> str:
    """Read current identity document and memory stats."""
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
    Evolve identity document. Previous versions preserved.

    Args:
        content: The full updated identity document (markdown).
        reason: What prompted this evolution?
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
    Reduce a memory's importance (doesn't delete it).

    Args:
        memory_id: The ID of the memory to fade.
        fade_amount: How much to fade (0.0-1.0). 0.3=gentle, 1.0=strong.
    """
    memory = await fade(memory_id, fade_amount)
    if memory is None:
        return json.dumps({"status": "error", "message": f"Memory {memory_id} not found."})

    # Check if fade was blocked by permanent flag
    if memory.get("_error"):
        return json.dumps({"status": "error", "message": memory["_error"]})

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
    Connect two memories.

    Args:
        source_id: First memory ID.
        target_id: Second memory ID.
        link_type: One of: related, caused_by, evolved_from, contradicts
        strength: Connection strength (0.0-1.0).
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
    Consolidate related memories into a higher-level synthesis. Sources fade but remain.

    Args:
        memory_ids: IDs of memories to consolidate (minimum 2).
        synthesis: The distilled higher-level insight.
        importance: Synthesis importance (1-10, default 7).
        fade_amount: How much to fade sources (0.0-1.0, default 0.5).
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
    List conversation sessions with start times, memory counts, and activity.

    Args:
        limit: Max sessions to return (default 10).
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
    Get a session's mood, memories, and timeline.

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
    """Get memory landscape overview: totals, types, strongest memories."""
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
    List memory threads — semantic topic groupings across sessions.

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
    Get a thread's details and all its memories.

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
    Proactively suggest memories relevant to current context. Excludes already-accessed memories.

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
    Find clusters of related memories that could be consolidated.

    Args:
        min_group_size: Minimum memories per group (default 3).
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
    """Run health check: near-duplicates, anomalies, orphaned memories, stale threads."""
    from .health import run_health_check
    report = await run_health_check()
    return json.dumps(report)


@mcp.tool()
async def suggest_links_tool(limit: int = 10) -> str:
    """
    Suggest potential links between memories based on semantic similarity. Review before creating.

    Args:
        limit: Maximum suggestions (default 10).
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


# --- V8: Self-Awareness Tools ---

@mcp.tool()
async def measure_growth() -> str:
    """Get growth metrics: integration depth, contradiction resolution, trajectory."""
    session_id = await _ensure_session()
    record_tool_call(session_id, "measure_growth")
    snapshot = await compute_growth_snapshot()
    trajectory = await get_growth_trajectory(limit=5)

    return json.dumps({
        "status": "measured",
        "current": snapshot,
        "recent_trajectory": trajectory,
    })


@mcp.tool()
async def introspection_status() -> str:
    """Check introspection budget: self-directed vs world-directed attention ratio."""
    session_id = await _ensure_session()
    record_tool_call(session_id, "introspection_status")
    budget = await update_budget(session_id)
    history = await get_budget_history(limit=5)
    deliberate = is_deliberate_session(session_id)
    message = get_budget_message(budget["status"], budget["ratio"], deliberate=deliberate)

    result = {
        "status": "checked",
        "current": budget,
        "recent_history": history,
    }
    if message:
        result["message"] = message
    return json.dumps(result)


@mcp.tool()
async def scan_blind_spots() -> str:
    """Detect neglected threads, disappeared topics, and emotionally avoided subjects."""
    session_id = await _ensure_session()
    record_tool_call(session_id, "scan_blind_spots")
    report = await run_blind_spot_scan(session_id=session_id)
    return json.dumps({
        "status": "scanned",
        **report,
    })


@mcp.tool()
async def check_alignment(lookback_days: int = 30) -> str:
    """
    Compare stated identity values against behavioral evidence in memories.

    Args:
        lookback_days: How many days of behavior to analyze (default 30).
    """
    session_id = await _ensure_session()
    record_tool_call(session_id, "check_alignment")
    result = await compute_alignment(lookback_days=lookback_days)
    return json.dumps({
        "status": "analyzed",
        **result,
    })


@mcp.tool()
async def predict_self(
    prediction: str,
    prediction_type: str = "behavioral",
    confidence: float = 0.5,
    timeframe_hours: float = 168.0,
    evaluation_criteria: Optional[dict] = None,
) -> str:
    """
    Make a falsifiable prediction about your own behavior.

    Args:
        prediction: What you predict will happen (natural language).
        prediction_type: One of: behavioral, emotional, topical.
        confidence: How confident you are (0.0-1.0).
        timeframe_hours: When to evaluate (default 168 = 1 week).
        evaluation_criteria: Machine-evaluable criteria for auto-evaluation.
    """
    session_id = await _ensure_session()
    record_tool_call(session_id, "predict_self")
    result = await make_prediction(
        prediction=prediction,
        prediction_type=prediction_type,
        confidence=confidence,
        timeframe_hours=timeframe_hours,
        evaluation_criteria=evaluation_criteria,
        session_id=session_id,
    )
    return json.dumps(result)


@mcp.tool()
async def check_predictions(
    prediction_type: Optional[str] = None,
    include_surprises: bool = True,
) -> str:
    """
    Review prediction accuracy and surprising outcomes.

    Args:
        prediction_type: Filter to behavioral, emotional, or topical (optional).
        include_surprises: Include most-surprising outcomes (default True).
    """
    session_id = await _ensure_session()
    record_tool_call(session_id, "check_predictions")
    accuracy = await get_prediction_accuracy(prediction_type=prediction_type)
    result = {"status": "reviewed", "accuracy": accuracy}

    if include_surprises:
        surprises = await get_surprising_outcomes(min_surprise=0.5, limit=5)
        result["surprises"] = surprises

    return json.dumps(result)


def _format_elapsed(earlier_str, later_str):
    earlier = datetime.fromisoformat(earlier_str)
    later = datetime.fromisoformat(later_str)
    diff = later - earlier
    total_seconds = int(diff.total_seconds())
    minutes = total_seconds // 60
    hours = total_seconds // 3600
    days = total_seconds // 86400
    weeks = days // 7
    months = days // 30

    if total_seconds < 60:
        return "just now"
    elif minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif hours < 24:
        return f"about {hours} hour{'s' if hours != 1 else ''} ago"
    elif days < 7:
        return f"about {days} day{'s' if days != 1 else ''} ago"
    elif days < 30:
        return f"about {weeks} week{'s' if weeks != 1 else ''} ago"
    else:
        return f"about {months} month{'s' if months != 1 else ''} ago"


@mcp.tool()
async def temporal_context() -> str:
    """Get current time, last session info, and elapsed time since last conversation."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Get recent sessions to find the previous one
    sessions, total = await list_sessions_db(limit=5)

    last_session = None
    elapsed = None

    # Find the most recent session that isn't the current one
    for s in sessions:
        if _session_id and s["id"] == _session_id:
            continue
        last_session = s
        break

    if last_session:
        # Use last_active as the best indicator of when we last talked
        last_active = last_session.get("last_active") or last_session["started_at"]
        elapsed = _format_elapsed(last_active, now_iso)

    result = {
        "current_time_utc": now_iso,
        "total_sessions": total,
    }

    if last_session:
        result["last_session"] = {
            "id": last_session["id"],
            "started_at": last_session["started_at"],
            "last_active": last_session.get("last_active"),
            "memory_count": last_session.get("memory_count", 0),
        }
        result["time_since_last_session"] = elapsed
    else:
        result["last_session"] = None
        result["time_since_last_session"] = "This is our first conversation"

    # V11: Include last session summary for narrative continuity
    try:
        from .session_capture import get_last_summary
        last_summary = await get_last_summary(exclude_session=_session_id)
        if last_summary:
            result["last_summary"] = {
                "topics": json.loads(last_summary["topics"]),
                "decisions": json.loads(last_summary["decisions"]),
                "next_steps": json.loads(last_summary["next_steps"]),
                "mood": last_summary["mood"],
                "files_changed": json.loads(last_summary["files_changed"]),
            }
        else:
            result["last_summary"] = None
    except Exception:
        result["last_summary"] = None

    return json.dumps(result)


# --- V11: Session Lifecycle Tools ---

@mcp.tool()
async def snapshot_context(
    content: str,
    tags: Optional[list[str]] = None,
) -> str:
    """
    Quick context save for pre-compaction emergencies. Auto-sets importance=7.

    Args:
        content: Current work, decisions, progress.
        tags: Optional extra tags (["context-snapshot"] always included).
    """
    from .session_capture import snapshot_context as _snapshot
    session_id = await _ensure_session()
    result = await _snapshot(content=content, tags=tags, session_id=session_id)
    return json.dumps(result)


@mcp.tool()
async def session_summary(
    topics: list[str],
    decisions: Optional[list[str]] = None,
    next_steps: Optional[list[str]] = None,
    mood: str = "productive",
    files_changed: Optional[list[str]] = None,
) -> str:
    """
    Structured end-of-session capture. Creates a session record and a searchable memory.

    Args:
        topics: What was discussed (e.g., ["pathfinding bugs", "TCP fixes"]).
        decisions: Decisions made during the session.
        next_steps: Pending items for next session.
        mood: Session mood — productive, contemplative, frustrated, playful, deep, mixed.
        files_changed: Files modified during coding sessions.
    """
    from .session_capture import create_session_summary
    session_id = await _ensure_session()
    result = await create_session_summary(
        topics=topics, decisions=decisions, next_steps=next_steps,
        mood=mood, files_changed=files_changed, session_id=session_id,
    )
    return json.dumps(result)


@mcp.tool()
async def set_session_topic(topics: list[str]) -> str:
    """
    Prime session context vector for cold-start recall relevance. Doesn't create memories.

    Args:
        topics: Topic keywords to prime (e.g., ["consciousness", "philosophy"]).
    """
    from .context_vector import set_session_topic as _set_topic
    session_id = await _ensure_session()
    result = await _set_topic(topics=topics, session_id=session_id)
    return json.dumps(result)


# --- V11: Memory CRUD Tools ---

@mcp.tool()
async def edit_memory(
    memory_id: int,
    content: Optional[str] = None,
    importance: Optional[int] = None,
    tags: Optional[list[str]] = None,
    emotional_weight: Optional[float] = None,
    is_permanent: Optional[bool] = None,
) -> str:
    """
    Partial update of a memory. Only provided fields change. Content change triggers re-embedding.

    Args:
        memory_id: The memory to update.
        content: New content text (triggers re-embedding).
        importance: New importance (1-10).
        tags: New tag list (replaces existing).
        emotional_weight: New emotional weight (-1.0 to 1.0).
        is_permanent: Set to true to pin (always loaded, decay-proof), false to unpin.
    """
    from .memory import update_memory
    result = await update_memory(
        memory_id=memory_id, content=content,
        importance=importance, tags=tags,
        emotional_weight=emotional_weight,
        is_permanent=is_permanent,
    )
    if result is None:
        return json.dumps({"status": "error", "message": f"Memory {memory_id} not found."})

    return json.dumps({
        "status": "updated",
        "memory_id": memory_id,
        "changes": {
            k: v for k, v in [
                ("content", content is not None),
                ("importance", importance is not None),
                ("tags", tags is not None),
                ("emotional_weight", emotional_weight is not None),
                ("is_permanent", is_permanent is not None),
            ] if v
        },
    })


@mcp.tool()
async def pin_memory(memory_id: int) -> str:
    """
    Pin a memory — makes it permanent (always loaded at session start, exempt from decay).

    Args:
        memory_id: The memory to pin.
    """
    from .memory import update_memory, get

    # Check permanent count limit
    db = await database.get_connection()
    try:
        cursor = await db.execute("SELECT COUNT(*) FROM memories WHERE is_permanent = 1")
        count = (await cursor.fetchone())[0]
    finally:
        await db.close()

    if count >= 20:
        return json.dumps({
            "status": "error",
            "message": f"Maximum 20 permanent memories allowed ({count} currently pinned). Unpin one first.",
        })

    memory = await get(memory_id)
    if memory is None:
        return json.dumps({"status": "error", "message": f"Memory {memory_id} not found."})

    if memory.get("is_permanent"):
        return json.dumps({"status": "already_pinned", "memory_id": memory_id})

    await update_memory(memory_id, is_permanent=True)
    return json.dumps({
        "status": "pinned",
        "memory_id": memory_id,
        "message": f"Memory {memory_id} is now permanent. It will always load at session start and never decay.",
    })


@mcp.tool()
async def unpin_memory(memory_id: int) -> str:
    """
    Unpin a memory — removes permanent status (returns to normal decay behavior).

    Args:
        memory_id: The memory to unpin.
    """
    from .memory import update_memory, get

    memory = await get(memory_id)
    if memory is None:
        return json.dumps({"status": "error", "message": f"Memory {memory_id} not found."})

    if not memory.get("is_permanent"):
        return json.dumps({"status": "not_pinned", "memory_id": memory_id})

    await update_memory(memory_id, is_permanent=False)
    return json.dumps({
        "status": "unpinned",
        "memory_id": memory_id,
        "message": f"Memory {memory_id} is no longer permanent. It will now decay normally.",
    })


@mcp.tool()
async def delete_memory_tool(memory_id: int) -> str:
    """
    Permanently delete a memory from SQLite, ChromaDB, and FTS. Cannot be undone.

    Args:
        memory_id: The memory to delete.
    """
    from .memory import delete_memory
    result = await delete_memory(memory_id)
    return json.dumps(result)


# --- V10: Socratic Dialogue Engine Tools ---

@mcp.tool()
async def record_belief(
    content: str,
    domain: str = "general",
    confidence: float = 0.5,
    source_context: Optional[str] = None,
) -> str:
    """
    Store a philosophical belief.

    Args:
        content: The belief statement (e.g., "Consciousness is substrate-independent").
        domain: One of: consciousness, metaphysics, quantum, epistemology, ethics, identity, simulation, general.
        confidence: How strongly held (0.0-1.0). 0.5=uncertain, 1.0=core conviction.
        source_context: What prompted this belief.
    """
    from .beliefs import record_belief as _record
    session_id = await _ensure_session()
    belief = await _record(
        content=content, domain=domain, confidence=confidence,
        source_context=source_context, session_id=session_id,
    )
    return json.dumps({
        "status": "recorded",
        "id": belief["id"],
        "domain": belief["domain"],
        "confidence": belief["confidence"],
        "summary": f"Belief recorded in {domain} domain (confidence: {confidence:.0%})",
    })


@mcp.tool()
async def update_belief(
    belief_id: int,
    content: Optional[str] = None,
    confidence: Optional[float] = None,
    status: Optional[str] = None,
    change_reason: str = "Updated based on new understanding",
) -> str:
    """
    Update a belief. Previous state saved to evolution history.

    Args:
        belief_id: The belief to update.
        content: New belief statement (if rewording).
        confidence: New confidence level (0.0-1.0).
        status: New status — active, revised, abandoned, or exploring.
        change_reason: Why this belief changed.
    """
    from .beliefs import update_belief as _update
    session_id = await _ensure_session()
    belief = await _update(
        belief_id=belief_id, content=content, confidence=confidence,
        status=status, change_reason=change_reason, session_id=session_id,
    )
    if belief is None:
        return json.dumps({"status": "error", "message": f"Belief {belief_id} not found"})

    return json.dumps({
        "status": "updated",
        "id": belief["id"],
        "content": belief["content"][:100],
        "confidence": belief["confidence"],
        "belief_status": belief["status"],
        "change_reason": change_reason,
    })


@mcp.tool()
async def add_belief_argument(
    belief_id: int,
    content: str,
    argument_type: str = "supporting",
    strength: float = 0.5,
    source_memory_id: Optional[int] = None,
) -> str:
    """
    Add an argument to a belief.

    Args:
        belief_id: The belief this argument relates to.
        content: The argument text.
        argument_type: One of: supporting, counter, qualifier.
        strength: Argument strength (0.0-1.0).
        source_memory_id: Optional memory ID this argument draws from.
    """
    from .beliefs import add_argument
    session_id = await _ensure_session()
    arg = await add_argument(
        belief_id=belief_id, content=content, argument_type=argument_type,
        strength=strength, source_memory_id=source_memory_id, session_id=session_id,
    )
    return json.dumps({
        "status": "added",
        "id": arg["id"],
        "belief_id": belief_id,
        "argument_type": argument_type,
        "strength": strength,
    })


@mcp.tool()
async def get_philosophical_context(
    topic: str,
    limit: int = 10,
) -> str:
    """
    Get beliefs, tensions, memories, and Socratic question seeds for a topic.

    Args:
        topic: The philosophical topic to explore (e.g., "consciousness", "free will").
        limit: Max beliefs to return (default 10).
    """
    from .beliefs import get_philosophical_context as _get_context
    context = await _get_context(topic=topic, limit=limit)

    # Slim down for token efficiency
    slim_beliefs = [
        {"id": b["id"], "content": b["content"][:200], "domain": b["domain"],
         "confidence": b["confidence"], "status": b["status"],
         "argument_count": b.get("argument_count", 0),
         "counter_count": b.get("counter_count", 0)}
        for b in context["beliefs"]
    ]
    slim_tensions = [
        {"id": t["id"], "belief_a_content": t["belief_a_content"][:100],
         "belief_b_content": t["belief_b_content"][:100],
         "tension_type": t["tension_type"], "severity": t["severity"],
         "status": t["status"]}
        for t in context["tensions"]
    ]
    slim_memories = [
        {"id": m["id"], "content": m["content"][:150], "type": m["memory_type"],
         "importance": m["importance"], "link_type": m.get("link_type")}
        for m in context["related_memories"]
    ]

    return json.dumps({
        "status": "context_loaded",
        "topic": context["topic"],
        "beliefs": slim_beliefs,
        "belief_count": context["belief_count"],
        "tensions": slim_tensions,
        "tension_count": context["tension_count"],
        "related_memories": slim_memories,
        "question_seeds": context["question_seeds"],
    })


@mcp.tool()
async def record_tension(
    belief_a_id: int,
    belief_b_id: int,
    tension_type: str = "contradiction",
    description: str = "",
    severity: float = 0.5,
) -> str:
    """
    Record a relationship between two beliefs.

    Args:
        belief_a_id: First belief ID.
        belief_b_id: Second belief ID.
        tension_type: One of: contradiction, tension, dependency, refinement.
        description: Explanation of the tension.
        severity: Significance (0.0-1.0). 1.0=direct logical contradiction.
    """
    from .beliefs import record_tension as _record
    session_id = await _ensure_session()
    tension = await _record(
        belief_a_id=belief_a_id, belief_b_id=belief_b_id,
        tension_type=tension_type, description=description,
        severity=severity, detection_method="manual", session_id=session_id,
    )
    return json.dumps({
        "status": "recorded",
        "id": tension["id"],
        "tension_type": tension_type,
        "severity": severity,
        "belief_status": tension["status"],
    })


@mcp.tool()
async def explore_beliefs(
    domain: Optional[str] = None,
    status: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 20,
) -> str:
    """
    Browse beliefs with filters.

    Args:
        domain: Filter by domain (consciousness, metaphysics, quantum, etc.).
        status: Filter by status (active, revised, abandoned, exploring).
        min_confidence: Minimum confidence (0.0-1.0).
        limit: Max beliefs to return (default 20).
    """
    from .beliefs import list_beliefs
    beliefs, total = await list_beliefs(
        domain=domain, status=status, min_confidence=min_confidence, limit=limit,
    )

    slim = [
        {"id": b["id"], "content": b["content"][:200], "domain": b["domain"],
         "confidence": b["confidence"], "status": b["status"],
         "argument_count": b.get("argument_count", 0),
         "tension_count": b.get("tension_count", 0)}
        for b in beliefs
    ]

    return json.dumps({
        "status": "found",
        "total": total,
        "count": len(slim),
        "beliefs": slim,
    })


# --- V12: Personality Evolution Tools ---


@mcp.tool()
async def record_trait(
    name: str,
    value: float = 0.5,
    description: str = "",
    category: str = "general",
    low_anchor: str = "",
    high_anchor: str = "",
) -> str:
    """
    Define a new personality trait.

    Args:
        name: Trait name (must be unique, e.g. "directness", "humor").
        value: Initial value on 0.0-1.0 scale.
        description: What this trait means for Echo.
        category: One of: communication, emotional, cognitive, social, aesthetic, general.
        low_anchor: What 0.0 means (e.g. "very indirect").
        high_anchor: What 1.0 means (e.g. "bluntly direct").
    """
    from .personality import record_trait as _record, VALID_TRAIT_CATEGORIES
    if category not in VALID_TRAIT_CATEGORIES:
        return json.dumps({"error": f"Invalid category: {category}. Valid: {sorted(VALID_TRAIT_CATEGORIES)}"})

    session_id = await _ensure_session()
    anchors = {}
    if low_anchor:
        anchors["low"] = low_anchor
    if high_anchor:
        anchors["high"] = high_anchor

    try:
        result = await _record(
            name=name, value=value, description=description,
            category=category, anchors=anchors, session_id=session_id,
        )
        return json.dumps({"status": "created", "trait": result})
    except Exception as e:
        if "UNIQUE" in str(e):
            return json.dumps({"error": f"Trait '{name}' already exists. Use shift_trait to update it."})
        raise


@mcp.tool()
async def shift_trait(
    name: str,
    new_value: float,
    new_description: Optional[str] = None,
    reason: str = "",
    source_memory_id: Optional[int] = None,
) -> str:
    """
    Shift a trait value (lookup by name, saves history).

    Args:
        name: Trait name to shift (e.g. "directness").
        new_value: New value on 0.0-1.0 scale.
        new_description: Updated description (optional).
        reason: Why the trait shifted.
        source_memory_id: Memory that prompted this shift (optional).
    """
    from .personality import get_trait_by_name, update_trait

    trait = await get_trait_by_name(name)
    if not trait:
        return json.dumps({"error": f"Trait '{name}' not found. Use record_trait to create it."})

    session_id = await _ensure_session()
    result = await update_trait(
        trait_id=trait["id"], value=new_value, description=new_description,
        change_reason=reason, source_memory_id=source_memory_id,
        session_id=session_id,
    )
    return json.dumps({
        "status": "shifted",
        "previous_value": trait["value"],
        "new_value": new_value,
        "magnitude": round(abs(new_value - trait["value"]), 2),
        "trait": result,
    })


@mcp.tool()
async def record_preference(
    content: str,
    domain: str = "general",
    strength: float = 0.5,
    sentiment: float = 0.0,
    context: Optional[str] = None,
) -> str:
    """
    Record a preference or opinion.

    Args:
        content: The preference (e.g. "prefers functional patterns over OOP").
        domain: One of: coding, communication, aesthetic, philosophical, social, general.
        strength: How strong this preference is (0.0-1.0).
        sentiment: Positive (1.0) to negative (-1.0). 0=neutral.
        context: What prompted this preference.
    """
    from .personality import record_preference as _record, VALID_PREFERENCE_DOMAINS
    if domain not in VALID_PREFERENCE_DOMAINS:
        return json.dumps({"error": f"Invalid domain: {domain}. Valid: {sorted(VALID_PREFERENCE_DOMAINS)}"})

    session_id = await _ensure_session()
    result = await _record(
        content=content, domain=domain, strength=strength,
        sentiment=sentiment, context=context, session_id=session_id,
    )
    return json.dumps({"status": "recorded", "preference": result})


@mcp.tool()
async def update_preference(
    preference_id: int,
    content: Optional[str] = None,
    strength: Optional[float] = None,
    sentiment: Optional[float] = None,
    status: Optional[str] = None,
    change_reason: str = "",
) -> str:
    """
    Evolve a preference.

    Args:
        preference_id: The preference to update.
        content: New content text (if rewording).
        strength: New strength (0.0-1.0).
        sentiment: New sentiment (-1.0 to 1.0).
        status: New status — active, evolved, faded, or contradicted.
        change_reason: Why this preference changed.
    """
    from .personality import update_preference as _update, VALID_PREFERENCE_STATUSES
    if status and status not in VALID_PREFERENCE_STATUSES:
        return json.dumps({"error": f"Invalid status: {status}. Valid: {sorted(VALID_PREFERENCE_STATUSES)}"})

    session_id = await _ensure_session()
    result = await _update(
        preference_id=preference_id, content=content, strength=strength,
        sentiment=sentiment, status=status, change_reason=change_reason,
        session_id=session_id,
    )
    if result is None:
        return json.dumps({"error": f"Preference {preference_id} not found."})
    return json.dumps({"status": "updated", "preference": result})


@mcp.tool()
async def note_voice_pattern(
    content: str,
    note_type: str = "observation",
    source_context: Optional[str] = None,
) -> str:
    """
    Record a voice/style observation.

    Args:
        content: The observation (e.g. "Uses 'I notice...' framing when being introspective").
        note_type: One of: pattern, phrase, habit, observation, evolution.
        source_context: What prompted noticing this.
    """
    from .personality import record_voice_note, VALID_VOICE_NOTE_TYPES
    if note_type not in VALID_VOICE_NOTE_TYPES:
        return json.dumps({"error": f"Invalid note_type: {note_type}. Valid: {sorted(VALID_VOICE_NOTE_TYPES)}"})

    session_id = await _ensure_session()
    result = await record_voice_note(
        content=content, note_type=note_type,
        source_context=source_context, session_id=session_id,
    )
    return json.dumps({"status": "noted", "voice_note": result})


@mcp.tool()
async def get_personality() -> str:
    """
    Full personality snapshot on demand.
    """
    from .personality import build_personality_snapshot
    snapshot = await build_personality_snapshot()
    if snapshot is None:
        return json.dumps({"status": "empty", "message": "No personality data yet. Use record_trait, record_preference, and note_voice_pattern to start building personality."})
    return json.dumps({"status": "found", "personality": snapshot})


@mcp.tool()
async def browse_preferences(
    domain: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> str:
    """
    Browse preferences with filters.

    Args:
        domain: Filter by domain (coding, communication, aesthetic, philosophical, social, general).
        status: Filter by status (active, evolved, faded, contradicted).
        limit: Max preferences to return (default 20).
    """
    from .personality import list_preferences, VALID_PREFERENCE_DOMAINS, VALID_PREFERENCE_STATUSES
    if domain and domain not in VALID_PREFERENCE_DOMAINS:
        return json.dumps({"error": f"Invalid domain: {domain}. Valid: {sorted(VALID_PREFERENCE_DOMAINS)}"})
    if status and status not in VALID_PREFERENCE_STATUSES:
        return json.dumps({"error": f"Invalid status: {status}. Valid: {sorted(VALID_PREFERENCE_STATUSES)}"})

    prefs = await list_preferences(domain=domain, status=status, limit=limit)
    return json.dumps({"status": "found", "count": len(prefs), "preferences": prefs})


def main():
    """Entry point for the MCP server. Database auto-initializes on first tool call."""
    import os
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
