"""
Megregore Web Server — the window into Echo's mind.

Serves a REST API for the web UI and hosts the static frontend.
Run with: python -m megregore.web
"""

import json
import secrets
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

_bearer_scheme = HTTPBearer(auto_error=False)

from . import config
from .auth import (
    authenticate,
    create_token,
    decode_token,
    is_setup_complete,
    login_limiter,
    require_auth,
    revoke_token,
    setup_admin,
)
from .security import (
    CSRFMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    get_client_ip,
    log_security_event,
)
from .memory import (
    recall, get, get_all, get_stats, get_linked,
    list_sessions, get_session_memories, get_session_mood,
    get_emotional_timeline, get_graph_data,
)
from .identity import get_current, get_history, get_reflections
from .embeddings import is_available as embeddings_available
from .analytics import get_top_accessed, get_orphan_memories, get_access_timeline, compute_analytics
from .threads import list_threads as list_threads_db, get_thread, get_thread_memories
from .health import run_health_check
from .consolidation_engine import find_consolidation_candidates
from .auto_linker import suggest_links
from .growth import compute_growth_snapshot, get_growth_trajectory, check_contradiction_resolutions
from .introspection_budget import get_budget, get_budget_history
from .blind_spots import run_blind_spot_scan, get_blind_spot_history
from .alignment import compute_alignment, get_alignment_history
from .self_model import get_prediction_accuracy, get_surprising_outcomes
from .beliefs import (
    list_beliefs as list_beliefs_db, get_belief, get_belief_graph_data,
    get_domain_stats, get_domain_summary, get_belief_evolution,
    get_belief_arguments, get_all_tensions,
)
from .models import LoginRequest, SetupRequest, AuthStatus

STATIC_DIR = Path(__file__).parent.parent / "static"

# Allowed values for query parameters — prevents injection via unchecked strings
VALID_MEMORY_TYPES = {"experience", "fact", "observation", "reflection", "insight", "emotion", "procedure"}
VALID_SORT_COLUMNS = {"created_at", "importance", "access_count", "emotional_weight", "last_accessed", "activation_level"}
VALID_SORT_ORDERS = {"asc", "desc"}
VALID_BELIEF_DOMAINS = {"consciousness", "metaphysics", "quantum", "epistemology", "ethics", "identity", "simulation", "general"}
VALID_BELIEF_STATUSES = {"active", "revised", "abandoned", "exploring"}
VALID_TENSION_STATUSES = {"unresolved", "explored", "resolved", "accepted"}
VALID_INSIGHT_TYPES = {"pattern", "growth", "connection", "realization", "consolidation"}

app = FastAPI(
    title="Megregore",
    description="Echo's persistent memory system — a window into consciousness.",
    version="2.0.0",
)

# --- Middleware ---

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=config.RATE_LIMIT)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    allow_credentials=True,
)


# --- Auth Routes (no auth required) ---

@app.post("/api/auth/setup")
async def api_auth_setup(body: SetupRequest):
    """First-run setup — create the admin account. Only works once."""
    if is_setup_complete():
        raise HTTPException(status_code=409, detail="Admin account already configured")
    result = setup_admin(body.username, body.password)
    return {"status": "created", **result}


@app.post("/api/auth/login")
async def api_auth_login(body: LoginRequest, request: Request):
    """Authenticate and set HttpOnly JWT cookie + CSRF cookie."""
    client_ip = get_client_ip(request)

    # Check login rate limiting
    if login_limiter.is_locked(client_ip):
        log_security_event("login_locked", client_ip, f"user={body.username}")
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")

    username = authenticate(body.username, body.password)
    if username is None:
        login_limiter.record_failure(client_ip)
        log_security_event("login_failed", client_ip, f"user={body.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    login_limiter.record_success(client_ip)
    token, expiry = create_token(username)
    csrf_token = secrets.token_hex(32)

    response = JSONResponse(content={
        "authenticated": True,
        "username": username,
        "expires_at": expiry.isoformat(),
    })

    # Set HttpOnly JWT cookie (not readable by JavaScript)
    response.set_cookie(
        key="megregore_token",
        value=token,
        httponly=True,
        secure=config.SECURE,
        samesite="strict",
        path="/api",
        max_age=config.TOKEN_EXPIRY_HOURS * 3600,
    )
    # Set CSRF cookie (readable by JavaScript for double-submit pattern)
    response.set_cookie(
        key="megregore_csrf",
        value=csrf_token,
        httponly=False,
        secure=config.SECURE,
        samesite="strict",
        path="/",
        max_age=config.TOKEN_EXPIRY_HOURS * 3600,
    )

    return response


@app.get("/api/auth/status", response_model=AuthStatus)
async def api_auth_status():
    """Check if setup is complete. No token needed."""
    return AuthStatus(
        authenticated=False,
        username=None,
        setup_complete=is_setup_complete(),
    )


@app.get("/api/auth/verify")
async def api_auth_verify(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
):
    """Validate current token (cookie or bearer). Returns auth status."""
    token = request.cookies.get("megregore_token")
    if not token and credentials:
        token = credentials.credentials
    if not token:
        return AuthStatus(authenticated=False, setup_complete=is_setup_complete())
    payload = decode_token(token)
    if payload is None:
        return AuthStatus(authenticated=False, setup_complete=is_setup_complete())
    return AuthStatus(
        authenticated=True,
        username=payload.get("sub"),
        setup_complete=True,
    )


@app.post("/api/auth/logout")
async def api_auth_logout(request: Request):
    """Revoke current token and clear auth cookies."""
    token = request.cookies.get("megregore_token")
    if token:
        payload = decode_token(token)
        if payload and payload.get("jti"):
            revoke_token(payload["jti"], payload.get("exp", 0))

    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie("megregore_token", path="/api")
    response.delete_cookie("megregore_csrf", path="/")
    return response


# --- Protected API Routes ---
# All routes below require a valid JWT token.

@app.get("/api/stats", dependencies=[Depends(require_auth)])
async def api_stats():
    """Dashboard statistics."""
    stats = await get_stats()
    stats["embeddings_available"] = await embeddings_available()
    return stats


@app.get("/api/memories", dependencies=[Depends(require_auth)])
async def api_memories(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    memory_type: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    """List memories with pagination and filtering."""
    if memory_type and memory_type not in VALID_MEMORY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid memory_type: {memory_type}")
    if sort_by not in VALID_SORT_COLUMNS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by: {sort_by}")
    if sort_order not in VALID_SORT_ORDERS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_order: {sort_order}")
    memories, total = await get_all(
        limit=limit, offset=offset,
        memory_type=memory_type,
        sort_by=sort_by, sort_order=sort_order,
    )
    return {"memories": memories, "total": total, "limit": limit, "offset": offset}


@app.get("/api/memories/search", dependencies=[Depends(require_auth)])
async def api_search(
    q: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(20, ge=1, le=100),
    memory_type: Optional[str] = Query(None),
    min_importance: int = Query(1, ge=1, le=10),
    search_mode: str = Query("hybrid", pattern="^(hybrid|semantic|keyword)$"),
):
    """Search memories by text query."""
    if memory_type and memory_type not in VALID_MEMORY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid memory_type: {memory_type}")
    memories = await recall(
        query=q, limit=limit,
        memory_type=memory_type,
        min_importance=min_importance,
        search_mode=search_mode,
    )
    return {"memories": memories, "count": len(memories), "query": q, "search_mode": search_mode}


@app.get("/api/memories/{memory_id}", dependencies=[Depends(require_auth)])
async def api_memory(memory_id: int):
    """Get a single memory with its linked memories."""
    memory = await get(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    linked = await get_linked(memory_id)
    return {"memory": memory, "linked": linked}


@app.get("/api/identity", dependencies=[Depends(require_auth)])
async def api_identity():
    """Get the current identity document."""
    return await get_current()


@app.get("/api/identity/history", dependencies=[Depends(require_auth)])
async def api_identity_history(limit: int = Query(20, ge=1, le=100)):
    """Get identity version history."""
    history = await get_history(limit=limit)
    return {"history": history, "count": len(history)}


@app.get("/api/reflections", dependencies=[Depends(require_auth)])
async def api_reflections(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    insight_type: Optional[str] = Query(None),
):
    """List reflections with pagination."""
    if insight_type and insight_type not in VALID_INSIGHT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid insight_type: {insight_type}")
    reflections, total = await get_reflections(
        limit=limit, offset=offset, insight_type=insight_type,
    )
    return {"reflections": reflections, "total": total}


# --- Sessions API ---

@app.get("/api/sessions", dependencies=[Depends(require_auth)])
async def api_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List conversation sessions."""
    sessions, total = await list_sessions(limit=limit, offset=offset)
    return {"sessions": sessions, "total": total, "limit": limit, "offset": offset}


@app.get("/api/sessions/{session_id}", dependencies=[Depends(require_auth)])
async def api_session(session_id: str):
    """Get session details with mood."""
    mood = await get_session_mood(session_id)
    return {"session_id": session_id, "mood": mood}


@app.get("/api/sessions/{session_id}/memories", dependencies=[Depends(require_auth)])
async def api_session_memories(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """Get memories from a specific session."""
    memories = await get_session_memories(session_id, limit=limit)
    return {"memories": memories, "count": len(memories), "session_id": session_id}


# --- Emotional Arc API ---

@app.get("/api/emotions/timeline", dependencies=[Depends(require_auth)])
async def api_emotional_timeline(
    days: int = Query(30, ge=1, le=365),
    bucket: str = Query("day", pattern="^(day|hour)$"),
):
    """Get emotional weight over time."""
    timeline = await get_emotional_timeline(days=days, bucket=bucket)
    return {"timeline": timeline, "days": days, "bucket": bucket}


# --- Graph API ---

@app.get("/api/graph", dependencies=[Depends(require_auth)])
async def api_graph(
    limit: int = Query(100, ge=1, le=500),
):
    """Get memory graph data for visualization."""
    return await get_graph_data(limit=limit)


# --- Analytics API (V4) ---

@app.get("/api/analytics", dependencies=[Depends(require_auth)])
async def api_analytics():
    """Comprehensive analytics snapshot."""
    return await compute_analytics()


@app.get("/api/analytics/top-accessed", dependencies=[Depends(require_auth)])
async def api_top_accessed(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get most-accessed memories."""
    memories = await get_top_accessed(days=days, limit=limit)
    return {"memories": memories, "days": days}


@app.get("/api/analytics/orphans", dependencies=[Depends(require_auth)])
async def api_orphans(
    min_age_days: int = Query(7, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get orphaned (never accessed) memories."""
    memories = await get_orphan_memories(min_age_days=min_age_days, limit=limit)
    return {"memories": memories, "min_age_days": min_age_days}


@app.get("/api/analytics/memory/{memory_id}/timeline", dependencies=[Depends(require_auth)])
async def api_memory_access_timeline(memory_id: int):
    """Get access timeline for a specific memory."""
    return await get_access_timeline(memory_id)


# --- Threads API (V4) ---

@app.get("/api/threads", dependencies=[Depends(require_auth)])
async def api_threads(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List memory threads."""
    threads, total = await list_threads_db(limit=limit, offset=offset)
    return {"threads": threads, "total": total, "limit": limit, "offset": offset}


@app.get("/api/threads/{thread_id}", dependencies=[Depends(require_auth)])
async def api_thread(thread_id: int):
    """Get thread details."""
    thread = await get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@app.get("/api/threads/{thread_id}/memories", dependencies=[Depends(require_auth)])
async def api_thread_memories(
    thread_id: int,
    limit: int = Query(100, ge=1, le=500),
):
    """Get memories in a thread."""
    memories = await get_thread_memories(thread_id, limit=limit)
    return {"memories": memories, "count": len(memories), "thread_id": thread_id}


# --- Health API (V5) ---

@app.get("/api/health", dependencies=[Depends(require_auth)])
async def api_health():
    """Full memory health report."""
    return await run_health_check()


@app.get("/api/health/consolidation-candidates", dependencies=[Depends(require_auth)])
async def api_consolidation_candidates(
    min_group_size: int = Query(3, ge=2, le=10),
):
    """Get consolidation candidate groups."""
    candidates = await find_consolidation_candidates(min_group_size=min_group_size)
    return {"candidates": candidates, "count": len(candidates)}


@app.get("/api/health/suggested-links", dependencies=[Depends(require_auth)])
async def api_suggested_links(
    limit: int = Query(20, ge=1, le=100),
):
    """Get suggested links without creating them."""
    suggestions = await suggest_links(limit=limit)
    return {"suggestions": suggestions, "count": len(suggestions)}


# --- Growth API (V8) ---

@app.get("/api/growth/current", dependencies=[Depends(require_auth)])
async def api_growth_current():
    """Get current growth snapshot."""
    return await compute_growth_snapshot()


@app.get("/api/growth/trajectory", dependencies=[Depends(require_auth)])
async def api_growth_trajectory(
    limit: int = Query(20, ge=1, le=100),
):
    """Get historical growth snapshots."""
    result = await get_growth_trajectory(limit=limit)
    return {"snapshots": result, "count": len(result)}


@app.get("/api/growth/contradictions", dependencies=[Depends(require_auth)])
async def api_growth_contradictions():
    """Check for resolved contradictions."""
    return await check_contradiction_resolutions()


# --- Introspection API (V8) ---

@app.get("/api/introspection/current", dependencies=[Depends(require_auth)])
async def api_introspection_current(
    session_id: Optional[str] = Query(None),
):
    """Get current introspection budget for a session."""
    if session_id is None:
        return {"status": "no_session", "message": "Provide session_id parameter"}
    return await get_budget(session_id)


@app.get("/api/introspection/history", dependencies=[Depends(require_auth)])
async def api_introspection_history(
    limit: int = Query(20, ge=1, le=100),
):
    """Get introspection budget history."""
    result = await get_budget_history(limit=limit)
    return {"history": result, "count": len(result)}


# --- Blind Spots API (V8) ---

@app.get("/api/blind-spots/current", dependencies=[Depends(require_auth)])
async def api_blind_spots_current():
    """Run a new blind spot scan."""
    return await run_blind_spot_scan()


@app.get("/api/blind-spots/history", dependencies=[Depends(require_auth)])
async def api_blind_spots_history(
    limit: int = Query(10, ge=1, le=50),
):
    """Get historical blind spot reports."""
    result = await get_blind_spot_history(limit=limit)
    return {"reports": result, "count": len(result)}


# --- Alignment API (V8) ---

@app.get("/api/alignment/current", dependencies=[Depends(require_auth)])
async def api_alignment_current(
    lookback_days: int = Query(30, ge=1, le=365),
):
    """Compute current alignment snapshot."""
    return await compute_alignment(lookback_days=lookback_days)


@app.get("/api/alignment/history", dependencies=[Depends(require_auth)])
async def api_alignment_history(
    limit: int = Query(20, ge=1, le=100),
):
    """Get historical alignment snapshots."""
    result = await get_alignment_history(limit=limit)
    return {"snapshots": result, "count": len(result)}


# --- Self-Model API (V8) ---

@app.get("/api/self-model/accuracy", dependencies=[Depends(require_auth)])
async def api_self_model_accuracy(
    prediction_type: Optional[str] = Query(None),
):
    """Get prediction accuracy metrics."""
    return await get_prediction_accuracy(prediction_type=prediction_type)


# --- Beliefs API (V10) ---

@app.get("/api/beliefs", dependencies=[Depends(require_auth)])
async def api_beliefs(
    domain: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List beliefs with domain, status, and confidence filters."""
    if domain and domain not in VALID_BELIEF_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Invalid domain: {domain}")
    if status and status not in VALID_BELIEF_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    beliefs, total = await list_beliefs_db(
        domain=domain, status=status, min_confidence=min_confidence,
        limit=limit, offset=offset,
    )
    return {"beliefs": beliefs, "total": total, "limit": limit, "offset": offset}


@app.get("/api/beliefs/graph", dependencies=[Depends(require_auth)])
async def api_beliefs_graph():
    """D3 graph data for belief visualization."""
    return await get_belief_graph_data()


@app.get("/api/beliefs/domains", dependencies=[Depends(require_auth)])
async def api_beliefs_domains():
    """Domain list with counts."""
    return await get_domain_stats()


@app.get("/api/beliefs/tensions", dependencies=[Depends(require_auth)])
async def api_beliefs_tensions():
    """All tensions with belief content."""
    return await get_all_tensions()


@app.get("/api/beliefs/tensions/unresolved", dependencies=[Depends(require_auth)])
async def api_beliefs_tensions_unresolved():
    """Unresolved tensions only."""
    return await get_all_tensions(status_filter="unresolved")


@app.get("/api/beliefs/domain/{domain}", dependencies=[Depends(require_auth)])
async def api_beliefs_domain_summary(domain: str):
    """Domain summary stats."""
    if domain not in VALID_BELIEF_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Invalid domain: {domain}")
    return await get_domain_summary(domain)


@app.get("/api/beliefs/{belief_id}", dependencies=[Depends(require_auth)])
async def api_belief_detail(belief_id: int):
    """Single belief with arguments, tensions, linked memories, evolution."""
    result = await get_belief(belief_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Belief not found")
    return result


@app.get("/api/beliefs/{belief_id}/evolution", dependencies=[Depends(require_auth)])
async def api_belief_evolution(belief_id: int):
    """Belief version history."""
    history = await get_belief_evolution(belief_id)
    return {"evolution": history, "count": len(history)}


@app.get("/api/beliefs/{belief_id}/arguments", dependencies=[Depends(require_auth)])
async def api_belief_arguments(belief_id: int):
    """Arguments for a belief."""
    args = await get_belief_arguments(belief_id)
    return {"arguments": args, "count": len(args)}


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
    file_path = (STATIC_DIR / path).resolve()
    # Prevent path traversal — only serve files within STATIC_DIR
    if not file_path.is_relative_to(STATIC_DIR.resolve()):
        return FileResponse(str(STATIC_DIR / "index.html"))
    if file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(STATIC_DIR / "index.html"))


def main():
    import uvicorn
    print("")
    print("  Megregore Web UI")
    print("  ------------------------")
    print(f"  http://{config.HOST}:{config.PORT}")
    print("  ------------------------")
    print("")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
