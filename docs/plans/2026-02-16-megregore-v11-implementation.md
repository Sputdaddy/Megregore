# Megregore V11 "The Living Memory" — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Megregore push-based where it matters — session lifecycle engine, conversation-aware recall, and dashboard evolution.

**Architecture:** Three pillars implemented as independent modules that integrate with existing memory.py, mcp_server.py, and web.py. New `events.py` module for SSE. Session context vector built into existing `recall()` pipeline. Schema V9→V10 adds `session_summaries` table.

**Tech Stack:** Python 3.12, FastMCP, aiosqlite, ChromaDB (all-MiniLM-L6-v2), FastAPI, SSE via `asyncio.Queue`, vanilla JS frontend.

---

## Task 1: Schema Migration V9→V10

**Files:**
- Modify: `megregore/migrations.py` (append new function)
- Modify: `megregore/database.py:190,196` (import + call chain)
- Modify: `tests/conftest.py:19,24` (import + call in fixture)
- Test: `tests/test_migration_v10.py`

**Step 1: Write the failing test**

Create `tests/test_migration_v10.py`:

```python
import pytest
import aiosqlite

pytestmark = pytest.mark.asyncio


class TestMigrationV9ToV10:
    async def test_creates_session_summaries_table(self, db):
        """Migration should create session_summaries table."""
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_summaries'"
        )
        row = await cursor.fetchone()
        assert row is not None, "session_summaries table should exist"

    async def test_session_summaries_columns(self, db):
        """Table should have all expected columns."""
        cursor = await db.execute("PRAGMA table_info(session_summaries)")
        columns = {row[1] for row in await cursor.fetchall()}
        expected = {"id", "session_id", "topics", "decisions", "next_steps", "mood", "files_changed", "created_at"}
        assert expected == columns

    async def test_index_exists(self, db):
        """Index on session_id should exist."""
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_session_summaries_session'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_schema_version_bumped(self, db):
        """Schema version should be 10."""
        cursor = await db.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        )
        row = await cursor.fetchone()
        assert row[0] == "10"

    async def test_idempotent(self, db):
        """Running migration twice should be safe."""
        from megregore.migrations import migrate_v9_to_v10
        result = await migrate_v9_to_v10(db)
        assert result["status"] == "already_migrated"
```

**Step 2: Run test to verify it fails**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_migration_v10.py -v`
Expected: FAIL — `migrate_v9_to_v10` doesn't exist yet.

**Step 3: Write the migration**

Append to `megregore/migrations.py`:

```python
async def migrate_v9_to_v10(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v9 to v10.

    Adds session_summaries table for structured session lifecycle data.

    Idempotent — safe to call multiple times.
    """
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 9

    if current_version >= 10:
        logger.info("Database already at v10 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v10")

    # Create session_summaries table
    try:
        await db.execute("""
            CREATE TABLE session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                topics TEXT DEFAULT '[]',
                decisions TEXT DEFAULT '[]',
                next_steps TEXT DEFAULT '[]',
                mood TEXT DEFAULT 'productive',
                files_changed TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        logger.debug("Created session_summaries table")
    except aiosqlite.OperationalError as e:
        if "already exists" in str(e):
            logger.debug("session_summaries table already exists, skipping")
        else:
            raise

    # Index
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_summaries_session ON session_summaries(session_id)"
    )

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "10"),
    )
    logger.debug("Updated schema_meta to version 10")

    await db.commit()
    logger.info("Migration v9 -> v10 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 10,
    }
```

**Step 4: Wire migration into database.py**

In `megregore/database.py`:
- Line 190: Add `migrate_v9_to_v10` to the import
- Line 195: Add `await migrate_v9_to_v10(db)` after `migrate_v8_to_v9`
- Line 16: Change `SCHEMA_VERSION = 9` to `SCHEMA_VERSION = 10`

In `tests/conftest.py`:
- Line 19: Add `migrate_v9_to_v10` to the import
- Line 24: Add `await migrate_v9_to_v10(conn)` after `migrate_v8_to_v9`

**Step 5: Run test to verify it passes**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_migration_v10.py -v`
Expected: 5 PASSED

**Step 6: Run full test suite**

Run: `cd /d/Projects/Megregore && python -m pytest -v`
Expected: All existing tests still pass

**Step 7: Commit**

```bash
cd /d/Projects/Megregore
git add megregore/migrations.py megregore/database.py tests/conftest.py tests/test_migration_v10.py
git commit -m "feat: schema migration v9→v10 — add session_summaries table"
```

---

## Task 2: Session Capture Module

**Files:**
- Create: `megregore/session_capture.py`
- Modify: `megregore/mcp_server.py` (add 2 new tools: snapshot_context, session_summary)
- Test: `tests/test_session_capture.py`

**Step 1: Write the failing tests**

Create `tests/test_session_capture.py`:

```python
import pytest
import json

pytestmark = pytest.mark.asyncio


class TestSnapshotContext:
    async def test_creates_memory(self, mock_db, mock_embeddings):
        from megregore.session_capture import snapshot_context
        result = await snapshot_context(
            content="We were debugging the pathfinding system",
            session_id="test1234",
        )
        assert result["status"] == "captured"
        assert result["memory_id"] > 0

    async def test_defaults(self, mock_db, mock_embeddings):
        from megregore.session_capture import snapshot_context
        result = await snapshot_context(
            content="Quick context save",
            session_id="test1234",
        )
        # Should have importance 7 and type experience
        from megregore.memory import get
        mem = await get(result["memory_id"])
        assert mem["importance"] == 7
        assert mem["memory_type"] == "experience"
        assert "context-snapshot" in mem["tags"]

    async def test_custom_tags(self, mock_db, mock_embeddings):
        from megregore.session_capture import snapshot_context
        result = await snapshot_context(
            content="Saving with custom tags",
            tags=["megregore", "v11"],
            session_id="test1234",
        )
        from megregore.memory import get
        mem = await get(result["memory_id"])
        assert "context-snapshot" in mem["tags"]
        assert "megregore" in mem["tags"]
        assert "v11" in mem["tags"]


class TestSessionSummary:
    async def test_creates_summary_record(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary
        result = await create_session_summary(
            topics=["pathfinding", "TCP connections"],
            session_id="test1234",
        )
        assert result["status"] == "summarized"
        assert result["summary_id"] > 0

    async def test_stores_all_fields(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary
        from megregore import database
        result = await create_session_summary(
            topics=["megregore", "v11"],
            decisions=["use SSE for events", "hard delete for memories"],
            next_steps=["implement events.py", "add mobile CSS"],
            mood="productive",
            files_changed=["memory.py", "mcp_server.py"],
            session_id="test1234",
        )
        db = await database.get_connection()
        cursor = await db.execute(
            "SELECT * FROM session_summaries WHERE id = ?", (result["summary_id"],)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert json.loads(row["topics"]) == ["megregore", "v11"]
        assert json.loads(row["decisions"]) == ["use SSE for events", "hard delete for memories"]
        assert json.loads(row["next_steps"]) == ["implement events.py", "add mobile CSS"]
        assert row["mood"] == "productive"
        assert json.loads(row["files_changed"]) == ["memory.py", "mcp_server.py"]

    async def test_also_creates_memory(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary
        result = await create_session_summary(
            topics=["testing"],
            session_id="test1234",
        )
        assert result["memory_id"] > 0

    async def test_defaults(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary
        from megregore import database
        result = await create_session_summary(
            topics=["quick test"],
            session_id="test1234",
        )
        db = await database.get_connection()
        cursor = await db.execute(
            "SELECT * FROM session_summaries WHERE id = ?", (result["summary_id"],)
        )
        row = await cursor.fetchone()
        assert json.loads(row["decisions"]) == []
        assert json.loads(row["next_steps"]) == []
        assert row["mood"] == "productive"


class TestGetLastSummary:
    async def test_returns_none_when_empty(self, mock_db):
        from megregore.session_capture import get_last_summary
        result = await get_last_summary()
        assert result is None

    async def test_returns_latest(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary, get_last_summary
        await create_session_summary(topics=["first"], session_id="sess1")
        await create_session_summary(topics=["second"], session_id="sess2")
        result = await get_last_summary()
        assert result is not None
        assert json.loads(result["topics"]) == ["second"]

    async def test_excludes_current_session(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary, get_last_summary
        await create_session_summary(topics=["old"], session_id="sess1")
        await create_session_summary(topics=["current"], session_id="sess2")
        result = await get_last_summary(exclude_session="sess2")
        assert result is not None
        assert json.loads(result["topics"]) == ["old"]
```

**Step 2: Run test to verify it fails**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_session_capture.py -v`
Expected: FAIL — module doesn't exist yet.

**Step 3: Write session_capture.py**

Create `megregore/session_capture.py`:

```python
"""Session lifecycle capture for Megregore V11. Structured session summaries and context snapshots."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database
from .memory import store

logger = logging.getLogger("megregore.session_capture")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def snapshot_context(
    content: str,
    tags: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Minimal-friction context save for pre-compaction emergencies.

    Auto-sets importance=7, type=experience. Designed to be called fast
    when context is about to be lost.
    """
    merged_tags = ["context-snapshot"]
    if tags:
        merged_tags.extend(tags)

    memory = await store(
        content=content,
        memory_type="experience",
        importance=7,
        tags=merged_tags,
        source="context-snapshot",
        session_id=session_id,
    )

    logger.info("Context snapshot saved (memory_id=%d)", memory["id"])

    return {
        "status": "captured",
        "memory_id": memory["id"],
        "summary": f"Context snapshot saved (importance: 7/10)",
    }


async def create_session_summary(
    topics: list[str],
    decisions: Optional[list[str]] = None,
    next_steps: Optional[list[str]] = None,
    mood: str = "productive",
    files_changed: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Structured end-of-session capture.

    Creates a session_summaries record AND a memory (type=experience)
    so it participates in recall.
    """
    db = await database.get_connection()
    try:
        now = _now()
        topics_json = json.dumps(topics)
        decisions_json = json.dumps(decisions or [])
        next_steps_json = json.dumps(next_steps or [])
        files_json = json.dumps(files_changed or [])

        cursor = await db.execute(
            """INSERT INTO session_summaries
               (session_id, topics, decisions, next_steps, mood, files_changed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, topics_json, decisions_json, next_steps_json, mood, files_json, now),
        )
        summary_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    # Also create a memory so the summary participates in recall
    content_parts = [f"Session summary — Topics: {', '.join(topics)}"]
    if decisions:
        content_parts.append(f"Decisions: {', '.join(decisions)}")
    if next_steps:
        content_parts.append(f"Next steps: {', '.join(next_steps)}")
    content_parts.append(f"Mood: {mood}")

    memory = await store(
        content=". ".join(content_parts),
        memory_type="experience",
        importance=6,
        tags=["session-summary", mood],
        source="session-summary",
        session_id=session_id,
    )

    logger.info("Session summary saved (id=%d, memory_id=%d)", summary_id, memory["id"])

    return {
        "status": "summarized",
        "summary_id": summary_id,
        "memory_id": memory["id"],
        "topics": topics,
        "mood": mood,
    }


async def get_last_summary(exclude_session: Optional[str] = None) -> Optional[dict]:
    """Get the most recent session summary, optionally excluding a session."""
    db = await database.get_connection()
    try:
        if exclude_session:
            cursor = await db.execute(
                "SELECT * FROM session_summaries WHERE session_id != ? ORDER BY created_at DESC LIMIT 1",
                (exclude_session,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM session_summaries ORDER BY created_at DESC LIMIT 1"
            )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()
```

**Step 4: Run test to verify it passes**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_session_capture.py -v`
Expected: All PASSED

**Step 5: Add MCP tools**

In `megregore/mcp_server.py`, add after the temporal_context tool:

```python
@mcp.tool()
async def snapshot_context(
    content: str,
    tags: Optional[list[str]] = None,
) -> str:
    """
    Minimal-friction context save for pre-compaction emergencies.

    Auto-sets importance=7, type=experience. Designed to be called fast
    when context is about to be lost.

    Args:
        content: What's happening right now — current work, decisions, progress.
        tags: Optional extra tags (["context-snapshot"] is always included).
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
    Structured end-of-session capture. Call at end of meaningful conversations.

    Creates a session record AND a memory so it participates in recall.
    Replaces the informal "save a memory about what we did" pattern.

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
```

**Step 6: Run full test suite**

Run: `cd /d/Projects/Megregore && python -m pytest -v`
Expected: All tests pass

**Step 7: Commit**

```bash
cd /d/Projects/Megregore
git add megregore/session_capture.py megregore/mcp_server.py tests/test_session_capture.py
git commit -m "feat: session capture — snapshot_context + session_summary MCP tools"
```

---

## Task 3: Enhanced temporal_context

**Files:**
- Modify: `megregore/mcp_server.py` (update `temporal_context` tool)
- Test: `tests/test_temporal_context_v11.py`

**Step 1: Write the failing test**

Create `tests/test_temporal_context_v11.py`:

```python
import pytest
import json

pytestmark = pytest.mark.asyncio


class TestTemporalContextWithSummary:
    async def test_includes_last_summary(self, mock_db, mock_embeddings):
        """temporal_context should include the last session's summary."""
        from megregore.session_capture import create_session_summary
        from megregore.mcp_server import temporal_context

        await create_session_summary(
            topics=["pathfinding", "TCP fixes"],
            decisions=["use adjacent tiles"],
            next_steps=["test the fix"],
            mood="frustrated",
            session_id="prev_sess",
        )

        result_json = await temporal_context()
        result = json.loads(result_json)
        assert "last_summary" in result
        assert result["last_summary"] is not None
        assert result["last_summary"]["topics"] == ["pathfinding", "TCP fixes"]
        assert result["last_summary"]["mood"] == "frustrated"

    async def test_no_summary_returns_null(self, mock_db, mock_embeddings):
        """When no summaries exist, last_summary should be null."""
        from megregore.mcp_server import temporal_context
        result_json = await temporal_context()
        result = json.loads(result_json)
        assert result.get("last_summary") is None
```

**Step 2: Run test to verify it fails**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_temporal_context_v11.py -v`
Expected: FAIL — `last_summary` not in result.

**Step 3: Modify temporal_context**

In `megregore/mcp_server.py`, update the `temporal_context` tool function. After building `result`, before `return json.dumps(result)`, add:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_temporal_context_v11.py -v`
Expected: PASSED

**Step 5: Commit**

```bash
cd /d/Projects/Megregore
git add megregore/mcp_server.py tests/test_temporal_context_v11.py
git commit -m "feat: temporal_context now includes last session summary"
```

---

## Task 4: Conversation-Aware Recall (Session Context Vector)

**Files:**
- Modify: `megregore/memory.py` (add context vector logic to `recall()`)
- Create: `megregore/context_vector.py` (session context vector computation)
- Test: `tests/test_context_recall.py`

**Step 1: Write the failing tests**

Create `tests/test_context_recall.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


class TestSessionContextVector:
    async def test_compute_returns_none_when_no_memories(self, mock_db):
        from megregore.context_vector import compute_session_context_vector
        result = await compute_session_context_vector("no_session")
        assert result is None

    async def test_compute_returns_vector_with_accessed_memories(self, mock_db, mock_embeddings):
        """When memories have been accessed this session, compute a context vector."""
        from megregore.context_vector import compute_session_context_vector
        from megregore import database

        db = await database.get_connection()
        # Insert a session and a memory
        await db.execute(
            "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            ("ctx_sess", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        await db.execute(
            """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags,
               source, session_id, activation_level, last_activation_decay, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Test memory", "experience", 5, 0.0, "[]", "test", "ctx_sess", 1.0,
             "2026-01-01T00:00:00", "2026-01-01T00:00:00", "2026-01-01T00:00:00", 1),
        )
        # Log an access
        await db.execute(
            "INSERT INTO memory_access_log (memory_id, access_type, session_id, accessed_at) VALUES (?, ?, ?, ?)",
            (1, "recall", "ctx_sess", "2026-01-01T00:00:00"),
        )
        await db.commit()

        # Mock embeddings to return a known vector
        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._build_embed_text.return_value = "Test memory"
            mock_emb._model = True
            mock_emb._ensure_model = AsyncMock(return_value=True)

            import asyncio
            import numpy as np

            fake_vector = [0.1] * 384
            mock_emb._model = type("Model", (), {"encode": lambda self, text: type("Arr", (), {"tolist": lambda self: fake_vector})()})()

            result = await compute_session_context_vector("ctx_sess")
            # Should return a list of floats (the averaged vector)
            assert result is not None
            assert len(result) == 384


class TestContextBlending:
    async def test_blend_score(self):
        """Test the blending formula."""
        from megregore.context_vector import blend_context_score
        # With session_relevance=1.0 and search_score=0.5
        blended = blend_context_score(search_score=0.5, session_relevance=1.0)
        # 0.7 * 0.5 + 0.3 * 1.0 = 0.35 + 0.30 = 0.65
        assert abs(blended - 0.65) < 0.01

    async def test_blend_with_zero_context(self):
        """When no session context, search score passes through."""
        from megregore.context_vector import blend_context_score
        blended = blend_context_score(search_score=0.8, session_relevance=None)
        assert blended == 0.8


class TestSetSessionTopic:
    async def test_seeds_context_vector(self, mock_db, mock_embeddings):
        """set_session_topic should seed the session context with topic embeddings."""
        from megregore.context_vector import set_session_topic, _session_context_cache
        # Clear cache
        _session_context_cache.clear()

        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_model = AsyncMock(return_value=True)
            mock_emb._model = type("Model", (), {
                "encode": lambda self, text: type("Arr", (), {"tolist": lambda self: [0.5] * 384})()
            })()

            await set_session_topic(["consciousness", "philosophy"], session_id="topic_sess")
            assert "topic_sess" in _session_context_cache
```

**Step 2: Run test to verify it fails**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_context_recall.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Write context_vector.py**

Create `megregore/context_vector.py`:

```python
"""Conversation-aware recall — session context vector for V11."""

import asyncio
import json
import logging
from typing import Optional

from . import database
from . import embeddings

logger = logging.getLogger("megregore.context_vector")

# In-memory cache: session_id → averaged embedding vector (list[float])
_session_context_cache: dict[str, list[float]] = {}

# Configurable weights
SEARCH_WEIGHT = 0.7
CONTEXT_WEIGHT = 0.3
MAX_CONTEXT_MEMORIES = 10


async def compute_session_context_vector(session_id: str) -> Optional[list[float]]:
    """
    Compute a session context vector by averaging embeddings of recently
    accessed/created memories this session.

    Returns None if no memories have been accessed or embeddings are unavailable.
    """
    if not await embeddings._ensure_model():
        return None

    db = await database.get_connection()
    try:
        # Get last N memory IDs accessed/created this session
        cursor = await db.execute(
            """SELECT DISTINCT memory_id FROM memory_access_log
               WHERE session_id = ?
               ORDER BY accessed_at DESC
               LIMIT ?""",
            (session_id, MAX_CONTEXT_MEMORIES),
        )
        access_rows = await cursor.fetchall()
        memory_ids = [row[0] for row in access_rows]

        # Also include memories created this session
        cursor = await db.execute(
            "SELECT id FROM memories WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, MAX_CONTEXT_MEMORIES),
        )
        created_rows = await cursor.fetchall()
        for row in created_rows:
            if row[0] not in memory_ids:
                memory_ids.append(row[0])

        memory_ids = memory_ids[:MAX_CONTEXT_MEMORIES]

        if not memory_ids:
            return None

        # Fetch content for these memories
        placeholders = ",".join("?" * len(memory_ids))
        cursor = await db.execute(
            f"SELECT id, content, context FROM memories WHERE id IN ({placeholders})",
            memory_ids,
        )
        rows = await cursor.fetchall()

        if not rows:
            return None

        # Compute embeddings and average
        loop = asyncio.get_running_loop()
        vectors = []
        for row in rows:
            text = embeddings._build_embed_text(row["content"], row["context"])
            vec = await loop.run_in_executor(
                None,
                lambda t=text: embeddings._model.encode(t).tolist(),
            )
            vectors.append(vec)

        if not vectors:
            return None

        # Average all vectors
        dim = len(vectors[0])
        avg = [0.0] * dim
        for vec in vectors:
            for i in range(dim):
                avg[i] += vec[i]
        for i in range(dim):
            avg[i] /= len(vectors)

        # Cache the result
        _session_context_cache[session_id] = avg

        return avg
    finally:
        await db.close()


def blend_context_score(
    search_score: float,
    session_relevance: Optional[float],
) -> float:
    """
    Blend search score with session context relevance.

    final_score = SEARCH_WEIGHT * search_score + CONTEXT_WEIGHT * session_relevance

    When no session context is available, search_score passes through unchanged.
    """
    if session_relevance is None:
        return search_score
    return SEARCH_WEIGHT * search_score + CONTEXT_WEIGHT * session_relevance


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def set_session_topic(
    topics: list[str],
    session_id: str,
) -> dict:
    """
    Seed the session context vector from topic keywords.

    Useful at session start to prime recall relevance before any
    memories have been accessed.
    """
    if not await embeddings._ensure_model():
        return {"status": "unavailable", "message": "Embedding model not loaded"}

    loop = asyncio.get_running_loop()
    topic_text = " ".join(topics)
    vec = await loop.run_in_executor(
        None,
        lambda: embeddings._model.encode(topic_text).tolist(),
    )
    _session_context_cache[session_id] = vec

    logger.info("Session topic set: %s (session=%s)", topics, session_id)
    return {
        "status": "topic_set",
        "topics": topics,
        "session_id": session_id,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_context_recall.py -v`
Expected: All PASSED

**Step 5: Add set_session_topic MCP tool**

In `megregore/mcp_server.py`:

```python
@mcp.tool()
async def set_session_topic(topics: list[str]) -> str:
    """
    Optional explicit context priming for cold-start sessions.

    Seeds the session context vector before any memories have been accessed.
    Useful at session start to prime recall relevance immediately.
    Lightweight — just guides the recall boosting, doesn't create memories.

    Args:
        topics: Topic keywords to prime (e.g., ["consciousness", "philosophy"]).
    """
    from .context_vector import set_session_topic as _set_topic
    session_id = await _ensure_session()
    result = await _set_topic(topics=topics, session_id=session_id)
    return json.dumps(result)
```

**Step 6: Integrate into recall() — optional enhancement**

In `megregore/memory.py`, after the scoring loop (line ~314, after `memories.sort`), add session context blending. This is done by modifying the `recall()` function signature to accept an optional `session_id` parameter and blending context scores.

Add to `recall()` signature: `session_id: Optional[str] = None`

After the sort on line 314, before the `memories = memories[:limit]` line, insert:

```python
        # V11: Session context vector blending
        if session_id:
            try:
                from .context_vector import (
                    compute_session_context_vector, cosine_similarity,
                    blend_context_score, _session_context_cache,
                )
                context_vec = _session_context_cache.get(session_id)
                if context_vec is None:
                    context_vec = await compute_session_context_vector(session_id)

                if context_vec and memories:
                    # Re-score with context blending
                    loop = asyncio.get_running_loop()
                    for mem in memories:
                        text = embeddings._build_embed_text(mem["content"], mem.get("context"))
                        mem_vec = await loop.run_in_executor(
                            None,
                            lambda t=text: embeddings._model.encode(t).tolist() if embeddings._model else None,
                        )
                        if mem_vec:
                            ctx_sim = cosine_similarity(context_vec, mem_vec)
                            old_score = mem.get("_relevance", 0.0)
                            mem["_relevance"] = blend_context_score(old_score, ctx_sim)

                    # Re-sort after blending
                    memories.sort(key=lambda m: m.get("_relevance", 0.0), reverse=True)
            except Exception as e:
                logger.debug("Context vector blending skipped: %s", e)
```

Also add `import asyncio` at the top of memory.py if not present, and update the `recall_memories` MCP tool to pass `session_id`:

In `mcp_server.py`, update the `recall_memories` tool to pass the session:

```python
    session_id = await _ensure_session()
    memories = await recall(
        query=query,
        limit=limit,
        memory_type=memory_type,
        min_importance=min_importance,
        tags_filter=tags,
        search_mode=search_mode,
        session_id=session_id,
    )
```

**Step 7: Run full test suite**

Run: `cd /d/Projects/Megregore && python -m pytest -v`
Expected: All tests pass

**Step 8: Commit**

```bash
cd /d/Projects/Megregore
git add megregore/context_vector.py megregore/memory.py megregore/mcp_server.py tests/test_context_recall.py
git commit -m "feat: conversation-aware recall with session context vector"
```

---

## Task 5: Events Module (SSE Event Bus)

**Files:**
- Create: `megregore/events.py`
- Modify: `megregore/web.py` (add SSE endpoint)
- Test: `tests/test_events.py`

**Step 1: Write the failing tests**

Create `tests/test_events.py`:

```python
import pytest
import asyncio
import json

pytestmark = pytest.mark.asyncio


class TestEventBus:
    async def test_subscribe_and_publish(self):
        from megregore.events import EventBus
        bus = EventBus()
        queue = bus.subscribe()

        bus.publish("memory_created", {"id": 1, "type": "experience"})

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["event"] == "memory_created"
        assert event["data"]["id"] == 1

    async def test_multiple_subscribers(self):
        from megregore.events import EventBus
        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()

        bus.publish("test_event", {"value": 42})

        e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert e1["data"]["value"] == 42
        assert e2["data"]["value"] == 42

    async def test_unsubscribe(self):
        from megregore.events import EventBus
        bus = EventBus()
        queue = bus.subscribe()
        bus.unsubscribe(queue)

        bus.publish("test_event", {"value": 1})

        # Queue should be empty since we unsubscribed
        assert queue.empty()

    async def test_publish_formats_sse(self):
        from megregore.events import format_sse
        result = format_sse("memory_created", {"id": 5})
        assert "event: memory_created" in result
        assert '"id": 5' in result
        assert result.endswith("\n\n")


class TestGlobalBus:
    async def test_global_bus_exists(self):
        from megregore.events import event_bus
        assert event_bus is not None

    async def test_emit_convenience(self):
        from megregore.events import event_bus, emit
        queue = event_bus.subscribe()
        emit("memory_created", {"id": 99})
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["data"]["id"] == 99
        event_bus.unsubscribe(queue)
```

**Step 2: Run test to verify it fails**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_events.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Write events.py**

Create `megregore/events.py`:

```python
"""SSE event bus for Megregore V11. Simple in-process pub/sub for real-time dashboard updates."""

import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("megregore.events")


class EventBus:
    """Simple in-process event bus using asyncio.Queue per subscriber."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """Create a new subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        logger.debug("New subscriber (total: %d)", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
            logger.debug("Subscriber removed (total: %d)", len(self._subscribers))

    def publish(self, event_type: str, data: dict) -> None:
        """Publish an event to all subscribers."""
        event = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)
                logger.warning("Subscriber queue full, dropping")

        for q in dead_queues:
            self._subscribers.remove(q)


def format_sse(event_type: str, data: dict) -> str:
    """Format an event as an SSE string."""
    json_data = json.dumps(data)
    return f"event: {event_type}\ndata: {json_data}\n\n"


# Global singleton bus
event_bus = EventBus()


def emit(event_type: str, data: dict) -> None:
    """Convenience function to publish to the global bus."""
    event_bus.publish(event_type, data)
```

**Step 4: Run test to verify it passes**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_events.py -v`
Expected: All PASSED

**Step 5: Add SSE endpoint to web.py**

In `megregore/web.py`, add import and endpoint:

```python
# Add to imports at top
from starlette.responses import StreamingResponse

# Add endpoint before the static files section
@app.get("/api/events", dependencies=[Depends(require_auth)])
async def api_events():
    """SSE event stream for real-time dashboard updates."""
    from .events import event_bus, format_sse

    queue = event_bus.subscribe()

    async def event_generator():
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield format_sse(event["event"], event["data"])
        except asyncio.TimeoutError:
            # Send keepalive comment
            yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

Also add `import asyncio` at the top of web.py if not present.

**Step 6: Wire events into memory operations**

In `megregore/memory.py`, add event emissions at key points:

After a successful `store()` (after the `return` dict is built but before `finally`):
```python
        # V11: Emit event
        try:
            from .events import emit
            emit("memory_created", {
                "id": memory_id,
                "type": memory_type,
                "importance": importance,
                "preview": content[:100],
            })
        except Exception:
            pass
```

**Step 7: Run full test suite**

Run: `cd /d/Projects/Megregore && python -m pytest -v`
Expected: All pass

**Step 8: Commit**

```bash
cd /d/Projects/Megregore
git add megregore/events.py megregore/web.py megregore/memory.py tests/test_events.py
git commit -m "feat: SSE event bus with /api/events endpoint"
```

---

## Task 6: Memory CRUD (Update + Delete)

**Files:**
- Modify: `megregore/memory.py` (add `update_memory()`, `delete_memory()`)
- Modify: `megregore/mcp_server.py` (add `edit_memory`, `delete_memory` tools)
- Modify: `megregore/web.py` (add PUT/DELETE endpoints)
- Test: `tests/test_memory_crud.py`

**Step 1: Write the failing tests**

Create `tests/test_memory_crud.py`:

```python
import pytest
import json

pytestmark = pytest.mark.asyncio


class TestUpdateMemory:
    async def test_update_content(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import update_memory, get
        result = await update_memory(1, content="Updated content")
        assert result is not None
        assert result["content"] == "Updated content"
        # Verify persisted
        mem = await get(1)
        assert mem["content"] == "Updated content"

    async def test_update_importance(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import update_memory, get
        await update_memory(1, importance=10)
        mem = await get(1)
        assert mem["importance"] == 10

    async def test_update_tags(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import update_memory, get
        await update_memory(1, tags=["new-tag", "updated"])
        mem = await get(1)
        assert "new-tag" in mem["tags"]
        assert "updated" in mem["tags"]

    async def test_update_emotional_weight(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import update_memory, get
        await update_memory(1, emotional_weight=-0.5)
        mem = await get(1)
        assert mem["emotional_weight"] == -0.5

    async def test_partial_update(self, mock_db, mock_embeddings, sample_memories):
        """Only provided fields should change."""
        from megregore.memory import update_memory, get
        original = await get(1)
        await update_memory(1, importance=3)
        mem = await get(1)
        assert mem["importance"] == 3
        assert mem["content"] == original["content"]  # unchanged

    async def test_update_nonexistent(self, mock_db, mock_embeddings):
        from megregore.memory import update_memory
        result = await update_memory(9999, content="nope")
        assert result is None

    async def test_update_content_re_embeds(self, mock_db, mock_embeddings, sample_memories):
        """Changing content should trigger re-embedding."""
        from megregore.memory import update_memory
        from unittest.mock import AsyncMock, call
        import megregore.embeddings as emb
        emb.embed_and_store = AsyncMock(return_value=True)
        await update_memory(1, content="Totally new content")
        emb.embed_and_store.assert_called_once()


class TestDeleteMemory:
    async def test_delete_existing(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import delete_memory, get
        result = await delete_memory(1)
        assert result["status"] == "deleted"
        mem = await get(1)
        assert mem is None

    async def test_delete_nonexistent(self, mock_db, mock_embeddings):
        from megregore.memory import delete_memory
        result = await delete_memory(9999)
        assert result["status"] == "not_found"

    async def test_delete_removes_links(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import delete_memory, link_memories
        from megregore import database
        await link_memories(1, 2, "related")
        await delete_memory(1)
        db = await database.get_connection()
        cursor = await db.execute(
            "SELECT COUNT(*) FROM memory_links WHERE source_memory_id = 1 OR target_memory_id = 1"
        )
        count = (await cursor.fetchone())[0]
        assert count == 0

    async def test_delete_removes_access_log(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import delete_memory
        from megregore import database
        db = await database.get_connection()
        await db.execute(
            "INSERT INTO memory_access_log (memory_id, access_type, accessed_at) VALUES (1, 'recall', '2026-01-01')"
        )
        await db.commit()
        await delete_memory(1)
        cursor = await db.execute("SELECT COUNT(*) FROM memory_access_log WHERE memory_id = 1")
        count = (await cursor.fetchone())[0]
        assert count == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_memory_crud.py -v`
Expected: FAIL — functions don't exist.

**Step 3: Add update_memory and delete_memory to memory.py**

Append to `megregore/memory.py`:

```python
async def update_memory(
    memory_id: int,
    content: Optional[str] = None,
    importance: Optional[int] = None,
    tags: Optional[list[str]] = None,
    emotional_weight: Optional[float] = None,
) -> Optional[dict]:
    """
    Partial update of a memory. Only changes provided fields.
    Re-embeds in ChromaDB if content changes.
    """
    db = await database.get_connection()
    try:
        # Check memory exists
        cursor = await db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = await cursor.fetchone()
        if row is None:
            return None

        mem = dict(row)

        # Build SET clause dynamically
        updates = []
        params = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))
        if emotional_weight is not None:
            updates.append("emotional_weight = ?")
            params.append(emotional_weight)

        if not updates:
            mem["tags"] = json.loads(mem["tags"])
            return mem

        params.append(memory_id)
        sql = f"UPDATE memories SET {', '.join(updates)} WHERE id = ?"
        await db.execute(sql, params)
        await db.commit()

        # Re-embed if content changed
        if content is not None:
            await embeddings.embed_and_store(
                memory_id=memory_id,
                content=content,
                context=mem["context"],
                metadata={
                    "memory_type": mem["memory_type"],
                    "importance": importance if importance is not None else mem["importance"],
                },
            )

        # V11: Emit event
        try:
            from .events import emit
            emit("memory_updated", {"id": memory_id})
        except Exception:
            pass

        # Return updated memory
        cursor = await db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = await cursor.fetchone()
        result = dict(row)
        result["tags"] = json.loads(result["tags"])
        return result
    finally:
        await db.close()


async def delete_memory(memory_id: int) -> dict:
    """
    Hard delete a memory from SQLite, ChromaDB, and FTS.
    Removes associated links and access log entries.
    """
    db = await database.get_connection()
    try:
        # Check memory exists
        cursor = await db.execute("SELECT id FROM memories WHERE id = ?", (memory_id,))
        row = await cursor.fetchone()
        if row is None:
            return {"status": "not_found", "memory_id": memory_id}

        # Delete links
        await db.execute(
            "DELETE FROM memory_links WHERE source_memory_id = ? OR target_memory_id = ?",
            (memory_id, memory_id),
        )

        # Delete access log entries
        await db.execute(
            "DELETE FROM memory_access_log WHERE memory_id = ?",
            (memory_id,),
        )

        # Delete the memory (FTS trigger handles FTS cleanup)
        await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        await db.commit()

        # Remove from ChromaDB
        try:
            collection = await embeddings._ensure_collection()
            if collection:
                import asyncio
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: collection.delete(ids=[str(memory_id)]),
                )
        except Exception:
            pass  # ChromaDB cleanup is best-effort

        # V11: Emit event
        try:
            from .events import emit
            emit("memory_deleted", {"id": memory_id})
        except Exception:
            pass

        return {"status": "deleted", "memory_id": memory_id}
    finally:
        await db.close()
```

**Step 4: Run test to verify it passes**

Run: `cd /d/Projects/Megregore && python -m pytest tests/test_memory_crud.py -v`
Expected: All PASSED

**Step 5: Add MCP tools**

In `megregore/mcp_server.py`:

```python
@mcp.tool()
async def edit_memory(
    memory_id: int,
    content: Optional[str] = None,
    importance: Optional[int] = None,
    tags: Optional[list[str]] = None,
    emotional_weight: Optional[float] = None,
) -> str:
    """
    Update a memory's content, importance, tags, or emotional weight.

    Only provided fields are changed. If content changes, the ChromaDB
    embedding is automatically updated.

    Args:
        memory_id: The memory to update.
        content: New content text (triggers re-embedding).
        importance: New importance (1-10).
        tags: New tag list (replaces existing tags).
        emotional_weight: New emotional weight (-1.0 to 1.0).
    """
    from .memory import update_memory
    result = await update_memory(
        memory_id=memory_id, content=content,
        importance=importance, tags=tags,
        emotional_weight=emotional_weight,
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
            ] if v
        },
    })


@mcp.tool()
async def delete_memory_tool(memory_id: int) -> str:
    """
    Permanently remove a memory from the system.

    Hard deletes from SQLite, ChromaDB, and FTS. Removes associated
    links and access log entries. This cannot be undone.

    Args:
        memory_id: The memory to delete.
    """
    from .memory import delete_memory
    result = await delete_memory(memory_id)
    return json.dumps(result)
```

**Step 6: Add web endpoints**

In `megregore/web.py`, add after the `api_memory` endpoint:

```python
@app.put("/api/memories/{memory_id}", dependencies=[Depends(require_auth)])
async def api_update_memory(memory_id: int, request: Request):
    """Partial update of a memory."""
    from .memory import update_memory
    body = await request.json()

    # Validate fields
    allowed_fields = {"content", "importance", "tags", "emotional_weight"}
    unknown = set(body.keys()) - allowed_fields
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown fields: {unknown}")

    if "importance" in body:
        imp = body["importance"]
        if not isinstance(imp, int) or imp < 1 or imp > 10:
            raise HTTPException(status_code=400, detail="importance must be 1-10")

    if "emotional_weight" in body:
        ew = body["emotional_weight"]
        if not isinstance(ew, (int, float)) or ew < -1.0 or ew > 1.0:
            raise HTTPException(status_code=400, detail="emotional_weight must be -1.0 to 1.0")

    result = await update_memory(memory_id, **body)
    if result is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return result


@app.delete("/api/memories/{memory_id}", dependencies=[Depends(require_auth)])
async def api_delete_memory(memory_id: int):
    """Permanently delete a memory."""
    from .memory import delete_memory
    result = await delete_memory(memory_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Memory not found")
    return result
```

**Step 7: Run full test suite**

Run: `cd /d/Projects/Megregore && python -m pytest -v`
Expected: All pass

**Step 8: Commit**

```bash
cd /d/Projects/Megregore
git add megregore/memory.py megregore/mcp_server.py megregore/web.py tests/test_memory_crud.py
git commit -m "feat: memory CRUD — edit_memory + delete_memory (MCP + web)"
```

---

## Task 7: Dashboard — SSE Activity Ticker

**Files:**
- Modify: `static/js/pages/Dashboard.js` (add activity ticker component)
- No tests needed (frontend visual)

**Step 1: Add SSE activity ticker to Dashboard.js**

At the top of the Dashboard page rendering, add a live activity feed:

```javascript
// SSE Activity Ticker component
function ActivityTicker() {
    const [events, setEvents] = useState([]);

    useEffect(() => {
        const token = getCookie('megregore_token');
        const evtSource = new EventSource('/api/events');

        evtSource.addEventListener('memory_created', (e) => {
            const data = JSON.parse(e.data);
            setEvents(prev => [{
                type: 'memory_created',
                text: `Memory #${data.id} created (${data.type}, importance: ${data.importance})`,
                preview: data.preview,
                time: new Date().toLocaleTimeString(),
            }, ...prev].slice(0, 20));
        });

        evtSource.addEventListener('memory_updated', (e) => {
            const data = JSON.parse(e.data);
            setEvents(prev => [{
                type: 'memory_updated',
                text: `Memory #${data.id} updated`,
                time: new Date().toLocaleTimeString(),
            }, ...prev].slice(0, 20));
        });

        evtSource.addEventListener('memory_deleted', (e) => {
            const data = JSON.parse(e.data);
            setEvents(prev => [{
                type: 'memory_deleted',
                text: `Memory #${data.id} deleted`,
                time: new Date().toLocaleTimeString(),
            }, ...prev].slice(0, 20));
        });

        return () => evtSource.close();
    }, []);

    if (events.length === 0) return null;

    return html`
        <div class="activity-ticker">
            <h3>Live Activity</h3>
            <div class="ticker-events">
                ${events.map((evt, i) => html`
                    <div class="ticker-event ticker-${evt.type}" key=${i}>
                        <span class="ticker-time">${evt.time}</span>
                        <span class="ticker-text">${evt.text}</span>
                    </div>
                `)}
            </div>
        </div>
    `;
}
```

**Step 2: Commit**

```bash
cd /d/Projects/Megregore
git add static/js/pages/Dashboard.js
git commit -m "feat: SSE activity ticker on Dashboard"
```

---

## Task 8: Dashboard — Memory Edit/Delete UI

**Files:**
- Modify: `static/js/pages/Memories.js` (add edit/delete buttons and forms)

**Step 1: Add edit/delete functionality**

Each memory card gets edit and delete buttons. Edit opens an inline form. Delete shows a confirmation dialog. Use `fetch` with PUT/DELETE to the API endpoints.

Key pieces:
- Edit button toggles inline form with pre-filled values
- Delete button shows `window.confirm()` dialog
- PUT `/api/memories/{id}` for updates
- DELETE `/api/memories/{id}` for deletion
- Refresh the memory list after changes

**Step 2: Commit**

```bash
cd /d/Projects/Megregore
git add static/js/pages/Memories.js
git commit -m "feat: memory edit/delete UI on Memories page"
```

---

## Task 9: Mobile-Responsive CSS

**Files:**
- Modify: `static/css/style.css` (add media queries)

**Step 1: Add responsive media queries**

```css
/* --- Mobile Responsive (V11) --- */
@media (max-width: 768px) {
    .sidebar {
        position: fixed;
        left: -250px;
        z-index: 1000;
        transition: left 0.3s ease;
    }
    .sidebar.open {
        left: 0;
    }
    .hamburger {
        display: block;
        position: fixed;
        top: 10px;
        left: 10px;
        z-index: 1001;
        background: var(--bg-secondary);
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 8px 12px;
        cursor: pointer;
        font-size: 1.2rem;
    }
    .main-content {
        margin-left: 0;
        padding: 10px;
    }
    .card {
        width: 100% !important;
    }
    .grid {
        grid-template-columns: 1fr !important;
    }
    .chart-container {
        overflow-x: auto;
    }
    h1 { font-size: 1.4rem; }
    h2 { font-size: 1.2rem; }
}
```

**Step 2: Add hamburger menu toggle**

In the main layout JS (likely `static/js/app.js` or the layout component), add a hamburger button that toggles `.sidebar.open`.

**Step 3: Commit**

```bash
cd /d/Projects/Megregore
git add static/css/style.css static/js/app.js
git commit -m "feat: mobile-responsive CSS with hamburger nav"
```

---

## Task 10: Final Integration & Verification

**Step 1: Run full test suite**

Run: `cd /d/Projects/Megregore && python -m pytest -v`
Expected: All tests pass.

**Step 2: Start MCP server and verify new tools**

Run: `cd /d/Projects/Megregore && python -m megregore.mcp_server`
Verify: 5 new tools appear (snapshot_context, session_summary, set_session_topic, edit_memory, delete_memory).
Total should be 34 tools.

**Step 3: Start web server and check endpoints**

Run: `cd /d/Projects/Megregore && python -m megregore.web`
Verify:
- `GET /api/events` returns SSE stream
- `PUT /api/memories/1` works with JSON body
- `DELETE /api/memories/1` works
- Dashboard shows activity ticker
- Memories page has edit/delete buttons
- Mobile responsive works at <768px

**Step 4: Commit and tag**

```bash
cd /d/Projects/Megregore
git add -A
git commit -m "feat: Megregore V11 'The Living Memory' complete"
git tag v11.0.0
```

---

## Execution Strategy

**Parallelizable tasks** (can be done simultaneously):
- Tasks 2+3 (session capture + enhanced temporal_context)
- Task 4 (context vector)
- Task 5 (events module)
- Task 6 (memory CRUD)

**Sequential dependencies:**
- Task 1 (migration) → everything else
- Tasks 5+6 → Tasks 7+8 (dashboard depends on backend)
- Task 9 (mobile CSS) is independent

**Delegation targets:**
- **DeepSeek**: Migration boilerplate (Task 1), CSS media queries (Task 9), test scaffolding
- **Kimi K2.5**: Context vector algorithm (Task 4), recall() integration logic
- **Sonnet agents**: Session capture module (Task 2), events module (Task 5), memory CRUD (Task 6)
- **Opus**: Architecture decisions, recall integration, review passes

## Summary

| Metric | Value |
|--------|-------|
| New MCP tools | 5 (snapshot_context, session_summary, set_session_topic, edit_memory, delete_memory) |
| New modules | 3 (session_capture.py, context_vector.py, events.py) |
| New tables | 1 (session_summaries) |
| New test files | 5 |
| Schema | V9→V10 |
| Total tools after V11 | 34 |
