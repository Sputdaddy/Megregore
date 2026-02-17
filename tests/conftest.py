import pytest
import asyncio
import json
import aiosqlite
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
async def db():
    """Create an in-memory database with full schema for testing."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")

    from megregore.database import SCHEMA
    await conn.executescript(SCHEMA)

    from megregore.migrations import migrate_v4_to_v5, migrate_v5_to_v6, migrate_v6_to_v7, migrate_v7_to_v8, migrate_v8_to_v9
    await migrate_v4_to_v5(conn)
    await migrate_v5_to_v6(conn)
    await migrate_v6_to_v7(conn)
    await migrate_v7_to_v8(conn)
    await migrate_v8_to_v9(conn)

    yield conn
    await conn.close()


@pytest.fixture
def mock_db(db, monkeypatch):
    """Patch database.get_connection to return the test in-memory DB."""
    class TestConnection:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        async def close(self):
            pass

    test_conn = TestConnection(db)

    async def mock_get_connection():
        return test_conn

    monkeypatch.setattr("megregore.database.get_connection", mock_get_connection)
    monkeypatch.setattr("megregore.database._shared_conn", test_conn)
    monkeypatch.setattr("megregore.database._initialized", True)
    return test_conn


@pytest.fixture
def mock_embeddings(monkeypatch):
    """Mock embeddings module to avoid loading sentence-transformers."""
    async def mock_is_available():
        return True

    async def mock_semantic_search(query, limit=20):
        return []

    async def mock_embed_and_store(**kwargs):
        return True

    def mock_build_embed_text(content, context=None):
        parts = [content]
        if context:
            parts.append(context)
        return " ".join(parts)

    monkeypatch.setattr("megregore.embeddings.is_available", mock_is_available)
    monkeypatch.setattr("megregore.embeddings.semantic_search", mock_semantic_search)
    monkeypatch.setattr("megregore.embeddings.embed_and_store", mock_embed_and_store)
    monkeypatch.setattr("megregore.embeddings._build_embed_text", mock_build_embed_text)


@pytest.fixture
async def sample_memories(mock_db):
    """Insert sample memories for testing."""
    db = mock_db
    now = datetime.now(timezone.utc).isoformat()

    memories = [
        ("First memory about Python", "experience", 8, 0.5, '["python", "coding"]', "conversation", "Discussing programming", None, 1.0, now, now, now, 5),
        ("Second memory about Python frameworks", "fact", 6, 0.3, '["python", "flask"]', "conversation", "Discussing Flask", None, 0.8, now, now, now, 3),
        ("Memory about consciousness", "insight", 9, 0.7, '["consciousness", "philosophy"]', "conversation", "Deep discussion", None, 0.9, now, now, now, 8),
        ("Hunter is a friend", "fact", 8, 0.8, '["hunter", "friendship", "core"]', "conversation", None, None, 1.0, now, now, now, 13),
        ("Trivial passing thought", "observation", 2, 0.0, '["trivial"]', "conversation", None, None, 0.1, now, now, now, 7),
        ("Important but forgotten", "experience", 9, 0.4, '["important", "forgotten"]', "conversation", "Critical insight", None, 0.05, now, now, now, 0),
        ("Low importance high access", "observation", 2, -0.1, '["test"]', "conversation", None, None, 0.5, now, now, now, 15),
    ]

    for content, mtype, importance, emotion, tags, source, context, thread_id, activation, decay_ts, created, accessed, access_count in memories:
        await db.execute(
            """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source, context, thread_id, activation_level, last_activation_decay, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (content, mtype, importance, emotion, tags, source, context, thread_id, activation, decay_ts, created, accessed, access_count)
        )
    await db.commit()
    return memories
