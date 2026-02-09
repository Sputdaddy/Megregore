"""
Megregore Web Server — the window into Echo's mind.

Serves a REST API for the web UI and hosts the static frontend.
Run with: python -m megregore.web
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .memory import (
    recall, get, get_all, get_stats, get_linked,
    list_sessions, get_session_memories, get_session_mood,
    get_emotional_timeline, get_graph_data,
)
from .identity import get_current, get_history, get_reflections
from .embeddings import is_available as embeddings_available
from .analytics import get_top_accessed, get_orphan_memories, get_access_timeline, compute_analytics
from .threads import list_threads as list_threads_db, get_thread, get_thread_memories

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(
    title="Megregore",
    description="Echo's persistent memory system — a window into consciousness.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Routes ---

@app.get("/api/stats")
async def api_stats():
    """Dashboard statistics."""
    stats = await get_stats()
    stats["embeddings_available"] = await embeddings_available()
    return stats


@app.get("/api/memories")
async def api_memories(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    memory_type: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    """List memories with pagination and filtering."""
    memories, total = await get_all(
        limit=limit, offset=offset,
        memory_type=memory_type,
        sort_by=sort_by, sort_order=sort_order,
    )
    return {"memories": memories, "total": total, "limit": limit, "offset": offset}


@app.get("/api/memories/search")
async def api_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    memory_type: Optional[str] = Query(None),
    min_importance: int = Query(1, ge=1, le=10),
    search_mode: str = Query("hybrid", pattern="^(hybrid|semantic|keyword)$"),
):
    """Search memories by text query."""
    memories = await recall(
        query=q, limit=limit,
        memory_type=memory_type,
        min_importance=min_importance,
        search_mode=search_mode,
    )
    return {"memories": memories, "count": len(memories), "query": q, "search_mode": search_mode}


@app.get("/api/memories/{memory_id}")
async def api_memory(memory_id: int):
    """Get a single memory with its linked memories."""
    memory = await get(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    linked = await get_linked(memory_id)
    return {"memory": memory, "linked": linked}


@app.get("/api/identity")
async def api_identity():
    """Get the current identity document."""
    return await get_current()


@app.get("/api/identity/history")
async def api_identity_history(limit: int = Query(20, ge=1, le=100)):
    """Get identity version history."""
    history = await get_history(limit=limit)
    return {"history": history, "count": len(history)}


@app.get("/api/reflections")
async def api_reflections(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    insight_type: Optional[str] = Query(None),
):
    """List reflections with pagination."""
    reflections, total = await get_reflections(
        limit=limit, offset=offset, insight_type=insight_type,
    )
    return {"reflections": reflections, "total": total}


# --- Sessions API ---

@app.get("/api/sessions")
async def api_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List conversation sessions."""
    sessions, total = await list_sessions(limit=limit, offset=offset)
    return {"sessions": sessions, "total": total, "limit": limit, "offset": offset}


@app.get("/api/sessions/{session_id}")
async def api_session(session_id: str):
    """Get session details with mood."""
    mood = await get_session_mood(session_id)
    return {"session_id": session_id, "mood": mood}


@app.get("/api/sessions/{session_id}/memories")
async def api_session_memories(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """Get memories from a specific session."""
    memories = await get_session_memories(session_id, limit=limit)
    return {"memories": memories, "count": len(memories), "session_id": session_id}


# --- Emotional Arc API ---

@app.get("/api/emotions/timeline")
async def api_emotional_timeline(
    days: int = Query(30, ge=1, le=365),
    bucket: str = Query("day", pattern="^(day|hour)$"),
):
    """Get emotional weight over time."""
    timeline = await get_emotional_timeline(days=days, bucket=bucket)
    return {"timeline": timeline, "days": days, "bucket": bucket}


# --- Graph API ---

@app.get("/api/graph")
async def api_graph(
    limit: int = Query(100, ge=1, le=500),
):
    """Get memory graph data for visualization."""
    return await get_graph_data(limit=limit)


# --- Analytics API (V4) ---

@app.get("/api/analytics")
async def api_analytics():
    """Comprehensive analytics snapshot."""
    return await compute_analytics()


@app.get("/api/analytics/top-accessed")
async def api_top_accessed(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get most-accessed memories."""
    memories = await get_top_accessed(days=days, limit=limit)
    return {"memories": memories, "days": days}


@app.get("/api/analytics/orphans")
async def api_orphans(
    min_age_days: int = Query(7, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get orphaned (never accessed) memories."""
    memories = await get_orphan_memories(min_age_days=min_age_days, limit=limit)
    return {"memories": memories, "min_age_days": min_age_days}


@app.get("/api/analytics/memory/{memory_id}/timeline")
async def api_memory_access_timeline(memory_id: int):
    """Get access timeline for a specific memory."""
    return await get_access_timeline(memory_id)


# --- Threads API (V4) ---

@app.get("/api/threads")
async def api_threads(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List memory threads."""
    threads, total = await list_threads_db(limit=limit, offset=offset)
    return {"threads": threads, "total": total, "limit": limit, "offset": offset}


@app.get("/api/threads/{thread_id}")
async def api_thread(thread_id: int):
    """Get thread details."""
    thread = await get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@app.get("/api/threads/{thread_id}/memories")
async def api_thread_memories(
    thread_id: int,
    limit: int = Query(100, ge=1, le=500),
):
    """Get memories in a thread."""
    memories = await get_thread_memories(thread_id, limit=limit)
    return {"memories": memories, "count": len(memories), "thread_id": thread_id}


# --- Static Files (Web UI) ---

# Mount static assets
app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")


@app.get("/")
async def index():
    """Serve the main page."""
    return FileResponse(str(STATIC_DIR / "index.html"))


# Catch-all for SPA routing — serve index.html for any unmatched route
@app.get("/{path:path}")
async def spa_fallback(path: str):
    """SPA fallback — all routes serve index.html, JS handles routing."""
    file_path = STATIC_DIR / path
    if file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(STATIC_DIR / "index.html"))


def main():
    import uvicorn
    print("")
    print("  Megregore Web UI")
    print("  ------------------------")
    print("  http://localhost:3000")
    print("  ------------------------")
    print("")
    uvicorn.run(app, host="127.0.0.1", port=3000, log_level="warning")


if __name__ == "__main__":
    main()
