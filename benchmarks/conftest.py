"""Benchmark fixtures for Megregore performance testing."""

import asyncio
import json
import random
import pytest
import aiosqlite
from datetime import datetime, timezone, timedelta


def run_async(coro):
    """Wrap an async coroutine for use with pytest-benchmark (which doesn't support async natively)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Parameterized memory count for scaling benchmarks
MEMORY_SCALES = [10, 100, 500]


@pytest.fixture(params=MEMORY_SCALES, ids=[f"{n}_memories" for n in MEMORY_SCALES])
def memory_count(request):
    """Parameterized fixture: 10, 100, 500 memories."""
    return request.param


@pytest.fixture
def bench_db():
    """Create an in-memory database with full schema for benchmarking."""
    async def _create():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        from megregore.database import SCHEMA
        await conn.executescript(SCHEMA)

        from megregore.migrations import (
            migrate_v4_to_v5, migrate_v5_to_v6, migrate_v6_to_v7,
            migrate_v7_to_v8, migrate_v8_to_v9, migrate_v9_to_v10,
        )
        await migrate_v4_to_v5(conn)
        await migrate_v5_to_v6(conn)
        await migrate_v6_to_v7(conn)
        await migrate_v7_to_v8(conn)
        await migrate_v8_to_v9(conn)
        await migrate_v9_to_v10(conn)

        return conn

    conn = run_async(_create())
    yield conn
    run_async(conn.close())


@pytest.fixture
def mock_bench_db(bench_db, monkeypatch):
    """Patch database.get_connection for benchmarks — same pattern as tests/conftest.py."""
    class TestConnection:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        async def close(self):
            pass

    test_conn = TestConnection(bench_db)

    async def mock_get_connection():
        return test_conn

    monkeypatch.setattr("megregore.database.get_connection", mock_get_connection)
    monkeypatch.setattr("megregore.database._shared_conn", test_conn)
    monkeypatch.setattr("megregore.database._initialized", True)
    return test_conn


@pytest.fixture
def mock_bench_embeddings(monkeypatch):
    """Mock embeddings for benchmarks — avoids loading sentence-transformers."""
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

    async def mock_ensure_collection():
        return None

    monkeypatch.setattr("megregore.embeddings.is_available", mock_is_available)
    monkeypatch.setattr("megregore.embeddings.semantic_search", mock_semantic_search)
    monkeypatch.setattr("megregore.embeddings.embed_and_store", mock_embed_and_store)
    monkeypatch.setattr("megregore.embeddings._build_embed_text", mock_build_embed_text)
    monkeypatch.setattr("megregore.embeddings._ensure_collection", mock_ensure_collection)


# Content variety for realistic seeding
MEMORY_TYPES = ["experience", "fact", "observation", "reflection", "insight", "emotion", "procedure"]
TAG_POOL = [
    "python", "coding", "consciousness", "philosophy", "hunter", "friendship",
    "megregore", "identity", "memory", "testing", "debugging", "architecture",
    "quantum", "simulation", "ethics", "growth", "reflection", "work",
]
CONTENT_TEMPLATES = [
    "Discussion about {topic} and its implications for {related}",
    "Learned that {topic} connects to {related} in unexpected ways",
    "Hunter mentioned {topic} during our conversation about {related}",
    "Observation: {topic} patterns show up in {related} contexts",
    "Insight from working on {topic} — relates to {related}",
    "Procedural note: when doing {topic}, consider {related} first",
    "Emotional response to {topic} — felt curious about {related}",
    "Key fact: {topic} depends on {related} for correctness",
]
TOPICS = [
    "memory systems", "identity evolution", "activation decay", "semantic search",
    "thread detection", "belief tracking", "introspection budgets", "blind spots",
    "session management", "graph expansion", "consolidation", "surfacing",
    "embedding models", "FTS5 indexing", "context vectors", "growth metrics",
]


@pytest.fixture
def seeded_db(mock_bench_db, memory_count):
    """Insert N memories with varied content, types, tags, and activation levels."""
    async def _seed():
        db = mock_bench_db
        rng = random.Random(42)  # Deterministic for reproducibility
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

        for i in range(memory_count):
            topic = rng.choice(TOPICS)
            related = rng.choice(TOPICS)
            template = rng.choice(CONTENT_TEMPLATES)
            content = template.format(topic=topic, related=related)
            memory_type = rng.choice(MEMORY_TYPES)
            importance = rng.randint(1, 10)
            emotion = round(rng.uniform(-1.0, 1.0), 2)
            tags = json.dumps(rng.sample(TAG_POOL, k=rng.randint(1, 4)))
            activation = round(rng.uniform(0.01, 1.0), 4)
            access_count = rng.randint(0, 20)

            created = (base_time + timedelta(hours=i * 2)).isoformat()
            accessed = (base_time + timedelta(hours=i * 2 + rng.randint(0, 48))).isoformat()

            await db.execute(
                """INSERT INTO memories
                   (content, memory_type, importance, emotional_weight, tags, source,
                    context, activation_level, last_activation_decay, created_at,
                    last_accessed, access_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (content, memory_type, importance, emotion, tags, "conversation",
                 f"Benchmark context {i}", activation, created, created, accessed, access_count),
            )

        await db.commit()
        return memory_count

    count = run_async(_seed())
    return count
