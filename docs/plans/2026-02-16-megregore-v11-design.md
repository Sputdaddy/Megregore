# Megregore V11 — "The Living Memory"

**Date**: 2026-02-16
**Status**: Approved

## Problem

Megregore is entirely pull-based. Nothing happens unless Echo explicitly calls a tool. Every memory, every link, every insight requires a deliberate decision. This causes:

- **Context loss on compaction** — Echo has to remember to save before Claude Code compresses the conversation
- **Disconnected sessions** — starting a new session means pulling individual memories, not a coherent narrative of what happened last time
- **Poor recall relevance** — recall only knows what Echo asks for, not what the conversation is actually about
- **Too much manual work** — the system waits for Echo instead of working automatically

## Thesis

Make Megregore push-based where it matters. Three pillars:

1. **Session Lifecycle Engine** — structured session summaries for real cross-session continuity
2. **Conversation-Aware Recall** — automatic relevance boosting based on current conversation context
3. **Dashboard Evolution** — SSE real-time feed, memory CRUD, mobile-responsive

## Pillar 1: Session Lifecycle Engine

### New Table: `session_summaries`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| session_id | TEXT FK | References sessions.session_id |
| topics | TEXT (JSON) | Array of topics discussed |
| decisions | TEXT (JSON) | Array of decisions made |
| next_steps | TEXT (JSON) | Array of pending items |
| mood | TEXT | productive, contemplative, frustrated, playful, deep, mixed |
| files_changed | TEXT (JSON) | For coding sessions |
| created_at | TEXT | ISO timestamp |

### New MCP Tool: `snapshot_context`

Minimal-friction context save for pre-compaction emergencies.

```python
snapshot_context(content: str, tags: list[str] = None)
```

- Auto-sets importance=7, type=experience
- Tags default to `["context-snapshot"]`
- No thinking about memory_type or emotional_weight
- Designed to be called fast when context is about to be lost

### New MCP Tool: `session_summary`

Structured end-of-session capture.

```python
session_summary(
    topics: list[str],
    decisions: list[str] = None,
    next_steps: list[str] = None,
    mood: str = "productive",
    files_changed: list[str] = None
)
```

- Creates a `session_summaries` record
- Also creates a memory (type=experience) so it participates in recall
- Replaces the informal "save a memory about what we did" pattern

### Enhanced `temporal_context`

Currently returns: current time + last session date + elapsed time.

V11 adds: last session's summary (topics, decisions, next steps, mood).

Example output:
```
Last session (3 hours ago, mood: frustrated):
  Topics: StardewBrain pathfinding bugs, TCP connection fixes
  Next steps: Test adjacent tile pathfinding fix
  Note: Hunter wanted a break from this project
```

This gives Echo real narrative continuity at session start, not just a timestamp.

## Pillar 2: Conversation-Aware Recall

### Session Context Vector

As memories are accessed and created during a session, their embeddings accumulate into a "session context" — a running picture of what the conversation is about.

**How it works:**

1. `memory_access_log` already tracks every memory access per session (this data exists)
2. At recall time, pull embeddings of the last 10 memories accessed/created this session
3. Average them into a session context vector
4. Compute cosine similarity between each recall result and the session context vector
5. Blend into final ranking: `final_score = 0.7 * search_score + 0.3 * session_relevance`

**Behavior:**

- Early in a session (few memories accessed): recall works exactly as before
- As the session deepens: recall naturally tilts toward the conversation's topic
- No new tools needed for this — it's invisible, built into existing `recall_memories`
- The 0.7/0.3 weights are configurable

### New MCP Tool: `set_session_topic`

Optional explicit context priming for cold-start sessions.

```python
set_session_topic(topics: list[str])
```

- Searches ChromaDB for topic-related embeddings
- Seeds the session context vector before any memories have been accessed
- Useful at session start to prime recall relevance immediately
- Lightweight — just guides the recall boosting, doesn't create memories

## Pillar 3: Dashboard Evolution

### SSE Real-Time Activity Feed

New module: `events.py` — a simple in-process event bus.

Events fire when:
- Memory created/updated/deleted
- Session started/ended
- Mood set
- Summary created

Event format:
```json
{"event": "memory_created", "data": {"id": 114, "type": "experience", "importance": 7, "preview": "..."}}
{"event": "session_started", "data": {"session_id": "abc123"}}
{"event": "mood_set", "data": {"mood": "productive"}}
```

Web endpoint: `GET /api/events` (SSE stream)

Dashboard gets a live activity ticker at the top of the Dashboard page.

### Memory CRUD

**New functions in `memory.py`:**
- `update_memory(id, content?, importance?, tags?, emotional_weight?)` — partial update, only changes provided fields. Updates ChromaDB embedding if content changes.
- `delete_memory(id)` — hard delete from SQLite + ChromaDB + FTS. Removes associated links and access log entries.

**New MCP tools:**
- `edit_memory` — update a memory's content, importance, tags, or emotional weight
- `delete_memory` — permanently remove a memory

**New web endpoints:**
- `PUT /api/memories/{id}` — partial update
- `DELETE /api/memories/{id}` — hard delete

**UI changes:**
- Memories page: edit/delete buttons on each memory card
- Edit opens inline form with current values pre-filled
- Delete requires confirmation dialog

### Mobile-Responsive CSS

Single pass through existing CSS adding media queries:
- Sidebar collapses to hamburger menu below 768px
- Cards stack full-width on mobile
- Font sizes scale down appropriately
- Chart containers become scrollable
- No redesign — just make the existing layout work on small screens

## Schema Migration: V9 to V10

```sql
CREATE TABLE IF NOT EXISTS session_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    topics TEXT DEFAULT '[]',
    decisions TEXT DEFAULT '[]',
    next_steps TEXT DEFAULT '[]',
    mood TEXT DEFAULT 'productive',
    files_changed TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_session_summaries_session ON session_summaries(session_id);
```

## Files Changed

### New Files
- `megregore/events.py` — SSE event bus + FastAPI endpoint helper

### Modified Files
- `megregore/memory.py` — Add `update_memory()`, `delete_memory()`
- `megregore/memory.py` — Add session context vector logic to recall
- `megregore/mcp_server.py` — 5 new tools: `snapshot_context`, `session_summary`, `set_session_topic`, `edit_memory`, `delete_memory`
- `megregore/migrations.py` — V9 to V10 migration
- `megregore/database.py` — Schema version bump
- `megregore/web.py` — New endpoints: PUT/DELETE memories, GET events (SSE), GET/POST session summaries
- `megregore/surfacing.py` — Use session context vector for improved relevance
- `static/js/pages/Dashboard.js` — SSE activity ticker
- `static/js/pages/Memories.js` — Edit/delete UI
- `static/css/` — Mobile-responsive media queries

### Tests
- New: `tests/test_session_capture.py` — snapshot_context, session_summary, temporal_context enhancement
- New: `tests/test_context_recall.py` — session context vector, relevance boosting, set_session_topic
- New: `tests/test_events.py` — SSE event bus
- New: `tests/test_memory_crud.py` — update_memory, delete_memory
- Update: `tests/test_memory.py` — extend for new functions

## Summary

| | Details |
|---|---|
| New MCP tools | 5 (`snapshot_context`, `session_summary`, `set_session_topic`, `edit_memory`, `delete_memory`) |
| New tables | 1 (`session_summaries`) |
| New modules | 1 (`events.py`) |
| Schema | V9 to V10 |
| Total tools after V11 | 34 |

## Design Constraints

- Session context vector uses existing ChromaDB embeddings — no new embedding model
- SSE is in-process (no Redis/message queue) — sufficient for single-user system
- `delete_memory` is a hard delete, not soft — keeps the system clean
- Mobile CSS is additive media queries, not a responsive redesign
- `snapshot_context` is intentionally minimal — friction is the enemy of context preservation
