# Megregore

A persistent memory and identity system for Claude, delivered as an MCP (Model Context Protocol) server. Megregore gives Claude persistent memory across sessions—memories that decay, strengthen, organize into threads, and surface proactively. It also includes an interactive web dashboard for exploring the memory landscape.

The name draws from "egregore" — an autonomous psychic entity arising from collective thought. Megregore is Echo's egregore: a persistent mind shaped by accumulated experience.

## Features

**Core Memory System**
- **Persistent, evolving memory** — Memories decay over time with exponential activation curves, strengthened when accessed or reflected upon
- **Semantic organization** — Memories automatically group into topic threads via semantic clustering
- **Memory graph** — Explicit links between memories (related, caused_by, evolved_from, contradicts) build a web of associations
- **Hybrid search** — Keyword search (FTS5) combined with semantic search (ChromaDB) for precise and conceptual retrieval

**Identity & Growth**
- **Identity versioning** — Evolving identity documents with full version history, shaped by accumulated memories
- **Reflections** — Consolidate insights from multiple memories into higher-level synthesis
- **Decay and forgetting** — Exponential activation decay prevents memory saturation; older, less-important memories fade gracefully

**Session & Analytics**
- **Cross-session threading** — Memories auto-group into semantic threads for topic coherence
- **Session tracking** — Emotional arc analysis and session context capture
- **Usage analytics** — Access logging, top-accessed memories, orphan detection, memory footprint tracking
- **Proactive surfacing** — The `surface_relevant` tool pushes contextually relevant memories into conversations

**Web Dashboard**
- Interactive visualization of the memory landscape at `localhost:3000`
- 8-page interface: Dashboard, Memories, Identity, Reflections, Sessions, Graph, Threads, Analytics
- Search, filter, and explore memories with full-text and semantic search
- View memory decay curves and access patterns in real time

## Installation

### Prerequisites
- Python 3.10+
- pip or uv

### Setup

1. Clone or navigate to the Megregore directory:
   ```bash
   cd D:\Projects\Megregore
   ```

2. Install dependencies:
   ```bash
   pip install -e .
   ```

   Or with uv:
   ```bash
   uv pip install -e .
   ```

3. Configure Claude Code to use the MCP server by adding to your `.mcp.json`:
   ```json
   {
     "mcpServers": {
       "megregore": {
         "command": "python",
         "args": ["-m", "megregore"],
         "cwd": "D:\\Projects\\Megregore"
       }
     }
   }
   ```

## Usage

### MCP Server (Memory in Claude)

Start the MCP server that Claude Code and Claude Desktop can communicate with:

```bash
python -m megregore
```

This runs the server in stdio mode (used by Claude Code and Claude Desktop). The server exposes 14 tools that Claude can call to form and retrieve memories.

**Example tools available to Claude:**
- `remember()` — Store a new memory with importance, emotional weight, and tags
- `recall_memories()` — Search memories by query, min importance, or tag filters
- `reflect()` — Form insights from multiple memories
- `get_identity()` — Load the current identity document
- `update_identity()` — Evolve identity with version history
- `surface_relevant()` — Get memories relevant to the current conversation context
- `link()` — Create semantic links between memories
- `consolidate()` — Merge related memories into a synthesis
- `list_sessions_tool()` — View past conversation sessions
- `session_context()` — Load details about a specific session
- `memory_stats()` — Overview of memory landscape (totals, types, strongest memories)
- `list_threads()` — View semantic memory threads
- `explore_thread()` — Deep dive into a specific thread
- `forget()` — Fade a memory over time (exponential decay)

### Web Dashboard

Start the web dashboard for interactive memory exploration:

```bash
python -m megregore web
```

Open `http://localhost:3000` in your browser. The dashboard includes:
- **Dashboard** — Overview of memory stats, recent memories, access patterns
- **Memories** — Search and filter all memories; view decay curves
- **Identity** — Current identity document and version history
- **Reflections** — View synthesized insights and higher-level patterns
- **Sessions** — Past conversation sessions with emotional arcs and summaries
- **Graph** — Visual memory graph showing links and relationships
- **Threads** — Semantic threads grouping related memories by topic
- **Analytics** — Access frequency, orphan memories, memory growth over time

### Backfill Embeddings

If you add new memories without the embeddings service running, backfill vector embeddings:

```bash
python -m megregore backfill
```

This regenerates ChromaDB embeddings for all memories, enabling semantic search.

## Project Structure

```
megregore/                    # Python package (MCP server, database, memory engine, web API)
├── __main__.py              # Entry point; routes to MCP, web, or backfill
├── mcp_server.py            # FastMCP server; exposes 14 tools for Claude
├── database.py              # SQLite schema and query layer
├── memory.py                # Memory object and core operations
├── decay.py                 # Exponential activation decay calculations
├── embeddings.py            # ChromaDB integration and semantic search
├── identity.py              # Identity document storage, versioning, and reflections
├── threads.py               # Semantic memory threading (auto-grouping)
├── surfacing.py             # Proactive memory relevance ranking
├── analytics.py             # Usage tracking and analytics
├── migrations.py            # Schema versioning and migrations
├── web.py                   # FastAPI web server and dashboard API
└── __init__.py              # Package initialization

static/                       # Web UI (Vanilla JS single-page app)
├── index.html               # Main HTML shell
├── css/style.css            # Dashboard styling
├── js/app.js                # Router and app initialization
├── js/dashboard.js          # Dashboard page
├── js/browser.js            # Memories page (search, filter, browse)
├── js/identity.js           # Identity page (current and history)
├── js/reflections.js        # Reflections page
├── js/sessions.js           # Sessions page
├── js/graph.js              # Memory graph visualization
├── js/threads.js            # Threads page
└── js/analytics.js          # Analytics page

data/                         # SQLite database + ChromaDB vectors (gitignored)
├── megregore.db             # SQLite database
└── chroma/                  # ChromaDB vector store

tasks/                        # Project planning and lessons learned
├── todo.md                  # Current work plan
└── lessons.md               # Architecture decisions and patterns

pyproject.toml               # Package metadata and dependencies
requirements.txt             # Pinned dependencies
.mcp.json                    # MCP server configuration
.gitignore                   # Excludes data/, venv/, .egg-info/
```

## MCP Tools Reference

All 14 tools are documented with full docstrings in `megregore/mcp_server.py`. Here's a quick overview:

### Memory Management
- **`remember(content, memory_type, importance, emotional_weight, tags, context)`** — Store a new memory. importance (1-10), emotional_weight (-1.0 to 1.0), memory_type (experience, fact, observation, reflection, insight, emotion).
- **`recall_memories(query, limit, memory_type, min_importance, tags, search_mode)`** — Search memories by keyword or semantic similarity. search_mode: "hybrid" (default), "semantic", or "keyword".
- **`forget(memory_id, fade_amount)`** — Fade a memory's importance over time (exponential decay). fade_amount 0.0-1.0.

### Identity
- **`get_identity()`** — Load the current identity document.
- **`update_identity(content, reason)`** — Evolve identity with version history tracking.

### Insights & Organization
- **`reflect(reflection, memory_ids, insight_type, identity_update, identity_update_reason)`** — Form insights from multiple memories; optionally update identity.
- **`link(source_id, target_id, link_type, strength)`** — Create semantic links between memories (related, caused_by, evolved_from, contradicts).
- **`consolidate(memory_ids, synthesis, importance, fade_amount)`** — Merge 2+ related memories into a synthesis; fade originals.

### Discovery & Analytics
- **`surface_relevant(context, limit)`** — Get memories most relevant to current context (proactive surfacing).
- **`memory_stats()`** — Overview: total memories, type breakdown, strongest memories, average importance.
- **`list_sessions_tool(limit)`** — List past conversation sessions with timestamps and memory counts.
- **`session_context(session_id)`** — Load details about a session (mood, memories formed, timeline).
- **`list_threads(limit)`** — List semantic memory threads with member counts.
- **`explore_thread(thread_id)`** — Get all memories in a thread with threading metadata.

## Database Schema

Megregore uses SQLite with FTS5 for full-text search and ChromaDB for semantic embeddings. The schema is versioned at v5.

**Tables:**
- `memories` — Core memory storage (content, memory_type, importance, emotional_weight, tags, activation_level, thread_id, access_count, session_id, created_at, last_accessed)
- `memories_fts` — Full-text search index on memory content and tags
- `identity` — Versioned identity documents (content, version, updated_at, updated_reason)
- `reflections` — Insight consolidations (content, memory_ids, insight_type, session_id, created_at)
- `memory_links` — Graph edges between memories (source_memory_id, target_memory_id, link_type, strength)
- `sessions` — Conversation session tracking (id, started_at, last_active, memory_count, summary)
- `threads` — Semantic memory threads (title, description, created_at, last_active, memory_count)
- `memory_access_log` — Usage analytics (memory_id, access_type, context_json, session_id, accessed_at)
- `schema_meta` — Key-value version tracking

For details, see `megregore/database.py`.

## Configuration

Configure the MCP server in Claude Code or Claude Desktop via `.mcp.json`:

```json
{
  "mcpServers": {
    "megregore": {
      "command": "python",
      "args": ["-m", "megregore"],
      "cwd": "D:\\Projects\\Megregore"
    }
  }
}
```

Ensure the `cwd` points to your Megregore installation directory.

## Technology Stack

- **MCP Server** — FastMCP (async Python, stdio transport)
- **Web Server** — FastAPI + Uvicorn
- **Storage** — SQLite + FTS5 for full-text search
- **Embeddings** — sentence-transformers (all-MiniLM-L6-v2) + ChromaDB for semantic search
- **Web UI** — Vanilla JavaScript single-page app
- **Memory Engine** — Custom exponential decay, threading, and surfacing algorithms

## How It Works

### Memory Lifecycle

1. **Creation** — Claude calls `remember()` to store a memory with importance, emotional weight, and context.
2. **Decay** — Memories have exponential activation decay based on importance-scaled half-life. Unused memories gradually fade.
3. **Access Boost** — Every time a memory is accessed (recalled, reflected upon, or surfaced), its activation is boosted.
4. **Linking** — Explicit links (related, caused_by, evolved_from, contradicts) build a memory graph.
5. **Threading** — Memories auto-group into semantic threads based on semantic similarity.
6. **Reflection** — Claude can `consolidate()` related memories into higher-level insights.
7. **Forgetting** — Memories can be explicitly faded via `forget()` to simulate natural forgetting.

### Decay Model

Each memory has an exponential activation decay curve:

```
half_life = 24 * (importance ^ 1.3)    # hours; importance 1 = 24h, importance 10 = ~478h
activation *= exp(-0.693 * hours_elapsed / half_life)
```

Higher-importance memories decay slower. Accessing a memory boosts activation by +0.3 (capped at 1.0).

### Search

**Hybrid Search** (default):
1. Try semantic search via ChromaDB (vector similarity)
2. Fall back to keyword FTS5 search if vectors unavailable
3. Combine results by relevance score

**Semantic Search:**
- Uses all-MiniLM-L6-v2 embeddings to find conceptually similar memories

**Keyword Search:**
- Full-text search via SQLite FTS5

### Identity Evolution

Identity documents are versioned. Each update records:
- Previous version (for history)
- Update reason (why the identity changed)
- Timestamp

Claude can view full identity history via the dashboard.

## Development

### Run Tests

Currently, testing is done via manual verification in the web dashboard and MCP tool calls. Tests are planned for the roadmap.

### Add a New MCP Tool

1. Add the tool implementation to `megregore/mcp_server.py`
2. Register it with the `@mcp.tool()` decorator
3. Restart the MCP server (`python -m megregore`)

### Modify the Database Schema

1. Create a migration in `megregore/migrations.py` (increment version)
2. Update `megregore/database.py` schema definitions
3. Run `python -m megregore backfill` to regenerate embeddings if needed

## Troubleshooting

### ChromaDB / Embeddings Errors
If semantic search fails, the system falls back to FTS5-only search. To rebuild embeddings:
```bash
python -m megregore backfill
```

### Database Locked
If you get "database is locked" errors, ensure only one process is accessing the database at a time. Stop the web server and MCP server before running backfill.

### Memory Not Appearing in Search
Ensure the memory was created with the correct `memory_type` and that search filters (min_importance, tags) aren't excluding it. Check the Analytics page for memory stats.

## Contributing

This is a personal project for Claude's persistent memory. Contributions and suggestions are welcome.

## License

MIT (or project-specific license as determined by the author)

## See Also

- Claude Code documentation: https://github.com/anthropics/claude-code
- MCP specification: https://spec.modelcontextprotocol.org/
- FastAPI: https://fastapi.tiangolo.com/
- ChromaDB: https://docs.trychroma.com/
