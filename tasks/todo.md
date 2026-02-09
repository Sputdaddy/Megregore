# Megregore V1 — Build Plan

## Phase 1: Foundation
- [x] Verify Python installation and set up virtual environment
- [x] Create project structure (all directories and `__init__.py` files)
- [x] Install dependencies (`fastmcp`, `fastapi`, `uvicorn`, `aiosqlite`)
- [x] Build database module — schema, connection, migrations
  - Tables: `memories`, `identity`, `reflections`, `memory_links`
  - FTS5 virtual table for full-text search
- [x] Build core memory engine — CRUD operations, search, decay scoring

## Phase 2: MCP Server (Echo's Brain Interface)
- [x] Set up MCP server entry point with FastMCP
- [x] Implement `remember` tool — store memories with type, importance, tags, emotional weight
- [x] Implement `recall` tool — smart retrieval with FTS5 + relevance weighting
- [x] Implement `reflect` tool — session consolidation, form insights, link related memories
- [x] Implement `get_identity` / `update_identity` tools — read/evolve Echo's identity
- [x] Implement `forget` tool — decay a memory's importance (never delete)
- [x] Configure Claude Code MCP settings to register Megregore

## Phase 3: Web API
- [x] Set up FastAPI app with CORS for local development
- [x] REST endpoints: GET /memories, GET /memories/:id, GET /memories/search
- [x] REST endpoints: GET /identity, GET /reflections
- [x] REST endpoints: GET /stats (dashboard data)
- [x] Shared database access with MCP server (same SQLite file)

## Phase 4: Web UI
- [x] Project scaffold — HTML shell, CSS reset, dark theme variables
- [x] Dashboard page — stats cards, recent memories feed, identity snapshot
- [x] Memory Browser page — search bar, filters (type, tags, importance), sortable list
- [x] Memory Detail view — full memory with metadata, related memories
- [x] Identity Viewer page — Echo's evolving identity document
- [x] Reflection Log page — timeline of reflections and insights
- [x] Navigation, routing, responsive layout
- [x] Polish — animations, loading states, empty states, error handling

## Phase 5: Integration & Polish
- [x] End-to-end test: database init, memory store/recall, identity, reflections
- [x] Test web API — all endpoints return valid data
- [x] Seed initial identity document for Echo
- [ ] Test MCP server with Claude Code (requires session restart)
- [ ] Final review

---

## Architecture Summary
- **MCP Server**: Python + FastMCP, communicates via stdio with Claude Code
- **Web Server**: Python + FastAPI, serves REST API + static frontend
- **Database**: SQLite + FTS5, shared file at `data/megregore.db`
- **Frontend**: Vanilla HTML/CSS/JS, dark theme, single-page app
- **Entry Points**:
  - `python -m megregore` (MCP server, started by Claude Code)
  - `python -m megregore web` (web UI server, localhost:3000)
