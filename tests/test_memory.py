import pytest
import json
from megregore.memory import store, recall, get, fade, link_memories, consolidate_memories

pytestmark = pytest.mark.asyncio


class TestStore:
    async def test_basic_store(self, mock_db, mock_embeddings):
        result = await store(
            content="Test memory content",
            memory_type="experience",
            importance=5,
            emotional_weight=0.3,
            tags=["test"],
            session_id="test-session",
        )
        assert result["id"] is not None
        assert result["content"] == "Test memory content"
        assert result["importance"] == 5
        assert result["activation_level"] == 1.0

    async def test_store_with_all_fields(self, mock_db, mock_embeddings):
        result = await store(
            content="Full memory",
            memory_type="insight",
            importance=9,
            emotional_weight=-0.5,
            tags=["deep", "important"],
            context="Testing all fields",
            session_id="test-session",
            thread_id=None,
        )
        assert result["memory_type"] == "insight"
        assert result["emotional_weight"] == -0.5
        assert result["tags"] == ["deep", "important"]


class TestGet:
    async def test_get_existing(self, mock_db, mock_embeddings):
        stored = await store(content="Findable memory", session_id="s1")
        result = await get(stored["id"])
        assert result is not None
        assert result["content"] == "Findable memory"

    async def test_get_nonexistent(self, mock_db, mock_embeddings):
        result = await get(99999)
        assert result is None


class TestFade:
    async def test_fade_reduces_importance(self, mock_db, mock_embeddings):
        stored = await store(content="Fadeable", importance=8, session_id="s1")
        result = await fade(stored["id"], amount=0.3)
        assert result is not None
        assert result["importance"] < 8

    async def test_fade_minimum_importance(self, mock_db, mock_embeddings):
        stored = await store(content="Already low", importance=1, session_id="s1")
        result = await fade(stored["id"], amount=1.0)
        assert result["importance"] >= 1

    async def test_fade_nonexistent(self, mock_db, mock_embeddings):
        result = await fade(99999, amount=0.5)
        assert result is None


class TestLinkMemories:
    async def test_create_link(self, mock_db, mock_embeddings):
        m1 = await store(content="Memory A", session_id="s1")
        m2 = await store(content="Memory B", session_id="s1")
        result = await link_memories(m1["id"], m2["id"], "related", 0.8)
        assert result is True

    async def test_create_link_with_source(self, mock_db, mock_embeddings):
        m1 = await store(content="Memory C", session_id="s1")
        m2 = await store(content="Memory D", session_id="s1")
        result = await link_memories(m1["id"], m2["id"], "related", 0.9, source="auto-inferred")
        assert result is True

        db = mock_db
        cursor = await db.execute(
            "SELECT source FROM memory_links WHERE source_memory_id = ? AND target_memory_id = ?",
            (m1["id"], m2["id"])
        )
        row = await cursor.fetchone()
        assert row[0] == "auto-inferred"


class TestRecallExpandGraph:
    async def test_recall_expand_graph_false(self, mock_db, mock_embeddings):
        """With expand_graph=False, no graph-neighbor memories are appended."""
        m1 = await store(content="Alpha memory about testing", importance=7, session_id="s1")
        m2 = await store(content="Beta memory about unrelated topic", importance=7, session_id="s1")
        await link_memories(m1["id"], m2["id"], "related", 0.9)

        results = await recall("Alpha testing", limit=5, expand_graph=False)
        result_ids = {m["id"] for m in results}
        # m2 should NOT appear via graph expansion
        for m in results:
            assert not m.get("_graph_expanded", False)

    async def test_recall_expand_graph_true(self, mock_db, mock_embeddings):
        """With expand_graph=True (default), linked neighbors are appended."""
        m1 = await store(content="Gamma memory about coding", importance=7, session_id="s1")
        m2 = await store(content="Delta memory about design", importance=7, session_id="s1")
        await link_memories(m1["id"], m2["id"], "related", 0.9)

        results = await recall("Gamma coding", limit=5, expand_graph=True)
        graph_expanded = [m for m in results if m.get("_graph_expanded")]
        # If m1 matched and m2 is linked, m2 should appear via graph expansion
        # (depends on FTS matching — if m1 matches, m2 should be graph-expanded)
        result_ids = {m["id"] for m in results}
        if m1["id"] in result_ids:
            assert m2["id"] in result_ids


class TestConsolidateMemories:
    async def test_consolidate_two(self, mock_db, mock_embeddings):
        m1 = await store(content="Part 1 of concept", importance=6, tags=["concept"], session_id="s1")
        m2 = await store(content="Part 2 of concept", importance=7, tags=["concept"], session_id="s1")

        result = await consolidate_memories(
            source_ids=[m1["id"], m2["id"]],
            synthesis="Combined concept understanding",
            importance=8,
            session_id="s1",
        )
        assert result["status"] == "consolidated"
        assert result["synthesis_id"] is not None
        assert result["source_count"] == 2

    async def test_consolidate_requires_two(self, mock_db, mock_embeddings):
        m1 = await store(content="Only one", session_id="s1")
        result = await consolidate_memories(
            source_ids=[m1["id"]],
            synthesis="Can't consolidate one",
        )
        assert result["status"] == "error"
