# Megregore

A persistent memory and identity system for Claude, delivered as an MCP (Model Context Protocol) server. Megregore gives Claude persistent memory across sessions—memories that decay, strengthen, organize into threads, and surface proactively. It also includes an interactive web dashboard for exploring the memory landscape.

The name draws from "egregore" — an autonomous psychic entity arising from collective thought. Megregore is Echo's egregore: a persistent mind shaped by accumulated experience.

## Features

**Core Memory System**
- **Persistent, evolving memory** — Memories decay over time with exponential activation curves, strengthened when accessed or reflected upon
- **Semantic organization** — Memories automatically group into topic threads via semantic clustering
- **Memory graph** — Explicit links between memories (related, caused_by, evolved_from, contradicts) build a web of associations
- **Hybrid search** — Keyword search (FTS5) combined with semantic search (ChromaDB) for precise and conceptual retrieval
- **Memory CRUD** — Full edit and delete support with re-embedding on content change and cascading cleanup

**Identity & Growth**
- **Identity versioning** — Evolving identity documents with full version history, shaped by accumulated memories
- **Reflections** — Consolidate insights from multiple memories into higher-level synthesis
- **Decay and forgetting** — Exponential activation decay prevents memory saturation; older, less-important memories fade gracefully
- **Growth metrics** — Integration depth, contradiction resolution tracking, and behavioral trajectory analysis

**Self-Awareness & Alignment (V7-V9)**
- **Introspection budget** — Tracks ratio of self-directed vs world-directed tool usage with contextual nudges
- **Blind spot detection** — Surfaces neglected threads, disappeared topics, and emotionally avoided subjects
- **Alignment checking** — Compares stated values in identity document against behavioral evidence in memories
- **Self-model predictions** — Falsifiable predictions about own behavior with accuracy tracking

**Philosophical Beliefs (V10)**
- **Belief graph** — Store beliefs with domain, confidence, and evolution history
- **Socratic dialogue** — Auto-generated question seeds from detected tensions and confidence extremes
- **Tension tracking** — Record contradictions, dependencies, and refinements between beliefs

**Session Lifecycle & Conversation-Aware Recall (V11)**
- **Session capture** — `snapshot_context` for pre-compaction emergencies, `session_summary` for structured end-of-session capture
- **Conversation-aware recall** — Session context vector boosts recall relevance based on what you've been discussing
- **SSE event bus** — Real-time push events for memory creation, updates, and deletions

**Session & Analytics**
- **Cross-session threading** — Memories auto-group into semantic threads for topic coherence
- **Session tracking** — Emotional arc analysis, session context capture, and session summaries with narrative continuity
- **Usage analytics** — Access logging, top-accessed memories, orphan detection, memory footprint tracking
- **Proactive surfacing** — The `surface_relevant` tool pushes contextually relevant memories into conversations

**Web Dashboard**
- Interactive visualization of the memory landscape at `localhost:3000`
- 13-page interface: Dashboard, Memories, Identity, Reflections, Sessions, Graph, Threads, Analytics, Health, Growth, Blind Spots, Self-Model, Beliefs
- Live SSE activity ticker showing real-time memory events
- Inline memory editing and deletion from the Memories page
- Mobile-responsive design with collapsible sidebar
- Search, filter, and explore memories with full-text and semantic search

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

This runs the server in stdio mode (used by Claude Code and Claude Desktop). The server exposes 36 tools that Claude can call to form, retrieve, and manage memories.

**Example tools available to Claude:**
- `remember()` — Store a new memory with importance, emotional weight, and tags
- `recall_memories()` — Search memories with conversation-aware context blending
- `reflect()` — Form insights from multiple memories
- `get_identity()` / `update_identity()` — Identity document with version history
- `session_start()` — Unified session initialization (identity + time + recent/important memories)
- `surface_relevant()` — Proactively surface memories relevant to current context
- `link()` / `consolidate()` — Build memory graph and merge related memories
- `forget()` — Fade a memory over time (exponential decay)
- `edit_memory()` / `delete_memory()` — Modify or remove existing memories
- `snapshot_context()` — Quick context save before compaction
- `session_summary()` — Structured end-of-session capture
- `set_session_topic()` — Prime recall relevance for current conversation
- `record_belief()` / `update_belief()` — Philosophical belief tracking
- `get_philosophical_context()` — Socratic question generation from belief tensions
- `introspection_status()` — Check self-directed vs world-directed attention ratio
- `check_alignment()` — Compare stated values against behavioral evidence
- `predict_self()` / `check_predictions()` — Falsifiable self-model predictions
- `scan_blind_spots()` — Detect neglected topics and avoided subjects
- `measure_growth()` — Integration depth and trajectory metrics
- ...and more (35 tools total)

### Web Dashboard

Start the web dashboard for interactive memory exploration:

```bash
python -m megregore web
```

Open `http://localhost:3000` in your browser. The dashboard includes:
- **Dashboard** — Neural Void aesthetic with stat cards, emotional arc chart, live SSE activity ticker
- **Memories** — Search, filter, edit, and delete memories with inline forms
- **Identity** — Current identity document and version history timeline
- **Reflections** — Synthesized insights and higher-level patterns
- **Sessions** — Past conversation sessions with emotional arcs and summaries
- **Graph** — Visual memory graph showing links and relationships
- **Threads** — Semantic threads grouping related memories by topic
- **Analytics** — Access frequency, orphan memories, memory growth over time
- **Health** — Memory health checks, consolidation candidates, suggested links
- **Growth** — Integration depth, contradiction resolution, trajectory metrics
- **Blind Spots** — Neglected topics and attention gap analysis
- **Self-Model** — Prediction accuracy and behavioral self-awareness
- **Beliefs** — Philosophical belief graph with tensions and evolution history

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
├── mcp_server.py            # FastMCP server; exposes 36 tools for Claude
├── database.py              # SQLite schema and query layer (v10)
├── memory.py                # Memory engine: store, recall, update, delete, link, consolidate
├── decay.py                 # Exponential activation decay calculations
├── embeddings.py            # ChromaDB integration and semantic search
├── identity.py              # Identity document storage, versioning, and reflections
├── threads.py               # Semantic memory threading (auto-grouping)
├── surfacing.py             # Proactive memory relevance ranking
├── analytics.py             # Usage tracking and analytics
├── migrations.py            # Schema versioning and migrations (v1→v10)
├── context_vector.py        # Session context vector for conversation-aware recall (V11)
├── session_capture.py       # Session lifecycle: snapshots and structured summaries (V11)
├── events.py                # SSE event bus for real-time dashboard updates (V11)
├── session_startup.py       # Unified session_start combining identity, time, and memories
├── beliefs.py               # Philosophical belief graph and Socratic dialogue (V10)
├── self_awareness.py        # Introspection, blind spots, alignment, self-model (V7-V9)
├── web.py                   # FastAPI web server and dashboard API
└── __init__.py              # Package initialization

static/                       # Web UI (Vue 3 single-page app)
├── index.html               # Main HTML shell
├── css/                     # Stylesheets (variables, base, layout, components, pages, dashboard-v2)
├── js/app.js                # Vue 3 bootstrap, router, API client, shared utilities
└── js/pages/                # Vue components (Dashboard, Memories, Identity, Reflections,
                             #   Sessions, Graph, Threads, Analytics, Health, Growth,
                             #   BlindSpots, SelfModel, Beliefs, Setup, Login)

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

All 36 tools are documented with full docstrings in `megregore/mcp_server.py`. Key categories:

### Memory Management
- **`remember`** — Store a new memory with type, importance (1-10), emotional weight (-1.0 to 1.0), and tags
- **`recall_memories`** — Hybrid search with conversation-aware context blending, configurable `content_length` (full/summary/brief), and optional `expand_graph` for linked neighbor discovery
- **`edit_memory`** — Partial update (content, importance, tags, emotional_weight) with re-embedding
- **`delete_memory`** — Hard delete from SQLite + ChromaDB + links + access log
- **`forget`** — Fade a memory's importance (exponential decay)

### Identity & Reflection
- **`get_identity`** / **`update_identity`** — Identity document with version history
- **`reflect`** — Form insights from multiple memories; optionally evolve identity
- **`link`** / **`consolidate`** — Build memory graph and merge related memories

### Session Lifecycle (V11)
- **`session_start`** — Unified session initialization: loads identity, temporal context, recent + important memories, and last session summary in one call
- **`temporal_context`** — Current time, last session gap, and previous session summary
- **`snapshot_context`** — Minimal-friction context save for pre-compaction emergencies
- **`session_summary`** — Structured end-of-session capture (topics, decisions, next steps, mood)
- **`set_session_topic`** — Prime conversation-aware recall with topic keywords

### Discovery & Analytics
- **`surface_relevant`** — Proactive memory surfacing based on current context
- **`memory_stats`** / **`memory_health`** — Landscape overview and health checks
- **`list_sessions_tool`** / **`session_context`** — Session history and details
- **`list_threads`** / **`explore_thread`** — Semantic thread exploration
- **`suggest_consolidations`** / **`suggest_links_tool`** — AI-suggested memory organization

### Self-Awareness (V7-V9)
- **`introspection_status`** — Self-directed vs world-directed attention ratio
- **`scan_blind_spots`** — Neglected topics and avoided subjects
- **`check_alignment`** — Stated values vs behavioral evidence
- **`predict_self`** / **`check_predictions`** — Falsifiable self-model predictions
- **`measure_growth`** — Integration depth and trajectory metrics

### Philosophical Beliefs (V10)
- **`record_belief`** / **`update_belief`** — Belief tracking with confidence and evolution history
- **`add_belief_argument`** — Supporting, counter, and qualifying arguments
- **`get_philosophical_context`** — Socratic question seeds from detected tensions
- **`record_tension`** / **`explore_beliefs`** — Belief graph navigation

## Database Schema

Megregore uses SQLite with FTS5 for full-text search and ChromaDB for semantic embeddings. The schema is versioned at **v10** with automatic migrations.

**Tables:**
- `memories` — Core memory storage with activation decay, threading, and session tracking
- `memories_fts` — Full-text search index on memory content and tags
- `identity` — Versioned identity documents with evolution history
- `reflections` — Insight consolidations linking multiple memories
- `memory_links` — Graph edges (related, caused_by, evolved_from, contradicts)
- `sessions` — Conversation session tracking with emotional arcs
- `session_summaries` — Structured session summaries (topics, decisions, next steps, mood) (V11)
- `threads` — Semantic memory threads (auto-grouping by topic)
- `memory_access_log` — Usage analytics and access patterns
- `beliefs` — Philosophical beliefs with domain, confidence, and status (V10)
- `belief_arguments` — Supporting, counter, and qualifying arguments for beliefs (V10)
- `belief_tensions` — Contradictions and dependencies between beliefs (V10)
- `self_predictions` — Falsifiable self-model predictions with evaluation (V9)
- `introspection_snapshots` — Self-directed attention ratio tracking (V7)
- `blind_spot_snapshots` — Neglected topic detection results (V8)
- `alignment_snapshots` — Value alignment check results (V8)
- `schema_meta` — Key-value version tracking

For details, see `megregore/database.py` and `megregore/migrations.py`.

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
- **Web UI** — Vue 3 single-page app with glassmorphic Neural Void aesthetic
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

```bash
python -m pytest -v
```

The test suite includes 239 tests covering memory operations, migrations, context vectors, session capture, events, CRUD operations, beliefs, self-awareness metrics, and more.

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
