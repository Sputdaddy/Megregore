import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestSurfaceRelevant:
    async def test_returns_empty_when_embeddings_unavailable(self, mock_db, mock_embeddings, monkeypatch):
        async def unavailable():
            return False

        monkeypatch.setattr("megregore.embeddings.is_available", unavailable)

        from megregore.surfacing import surface_relevant
        results = await surface_relevant("some context")
        assert results == []

    async def test_returns_empty_when_no_semantic_matches(self, mock_db, mock_embeddings):
        # mock_embeddings already makes semantic_search return []
        from megregore.surfacing import surface_relevant
        results = await surface_relevant("some context")
        assert results == []

    async def test_returns_scored_memories(self, mock_db, mock_embeddings, monkeypatch):
        from megregore.memory import store
        mem1 = await store(content="Test memory one", importance=8)
        mem2 = await store(content="Test memory two", importance=5)

        async def mock_search(query, limit=20):
            return [(mem1["id"], 0.9), (mem2["id"], 0.7)]

        monkeypatch.setattr("megregore.embeddings.semantic_search", mock_search)

        from megregore.surfacing import surface_relevant
        results = await surface_relevant("test context")

        assert len(results) == 2
        for r in results:
            assert "_surfacing_score" in r
            assert "_similarity" in r
        assert results[0]["_surfacing_score"] >= results[1]["_surfacing_score"]

    async def test_excludes_already_accessed_memories(self, mock_db, mock_embeddings, monkeypatch):
        from megregore.memory import store
        from megregore import database

        mem1 = await store(content="Should be excluded", importance=8)
        mem2 = await store(content="Should be returned", importance=7)

        # Log mem1 as already accessed in this session
        db = await database.get_connection()
        await db.execute(
            "INSERT INTO memory_access_log (memory_id, access_type, session_id, accessed_at) VALUES (?, ?, ?, ?)",
            (mem1["id"], "recall", "test-session-1", _now()),
        )
        await db.commit()

        async def mock_search(query, limit=20):
            return [(mem1["id"], 0.95), (mem2["id"], 0.80)]

        monkeypatch.setattr("megregore.embeddings.semantic_search", mock_search)

        from megregore.surfacing import surface_relevant
        results = await surface_relevant("test context", session_id="test-session-1")

        returned_ids = [r["id"] for r in results]
        assert mem1["id"] not in returned_ids
        assert mem2["id"] in returned_ids

    async def test_procedure_type_gets_boost(self, mock_db, mock_embeddings, monkeypatch):
        from megregore.memory import store
        mem_proc = await store(content="A procedure memory", importance=5, memory_type="procedure")
        mem_exp = await store(content="An experience memory", importance=5, memory_type="experience")

        # Give them identical similarity so only the type boost differentiates
        async def mock_search(query, limit=20):
            return [(mem_proc["id"], 0.7), (mem_exp["id"], 0.7)]

        monkeypatch.setattr("megregore.embeddings.semantic_search", mock_search)

        from megregore.surfacing import surface_relevant
        results = await surface_relevant("test context")

        assert len(results) == 2
        proc_result = next(r for r in results if r["id"] == mem_proc["id"])
        exp_result = next(r for r in results if r["id"] == mem_exp["id"])
        assert proc_result["_surfacing_score"] > exp_result["_surfacing_score"]

    async def test_limit_respected(self, mock_db, mock_embeddings, monkeypatch):
        from megregore.memory import store

        mem_ids = []
        for i in range(6):
            m = await store(content=f"Memory {i}", importance=5)
            mem_ids.append(m["id"])

        async def mock_search(query, limit=20):
            return [(mid, 0.8 - i * 0.05) for i, mid in enumerate(mem_ids)]

        monkeypatch.setattr("megregore.embeddings.semantic_search", mock_search)

        from megregore.surfacing import surface_relevant
        results = await surface_relevant("test context", limit=3)
        assert len(results) <= 3

    async def test_results_sorted_by_score_descending(self, mock_db, mock_embeddings, monkeypatch):
        from megregore.memory import store

        # Use varied importance to create score differences alongside similarity
        mem_low = await store(content="Low importance memory", importance=2)
        mem_mid = await store(content="Mid importance memory", importance=5)
        mem_high = await store(content="High importance memory", importance=9)

        async def mock_search(query, limit=20):
            return [
                (mem_low["id"], 0.6),
                (mem_mid["id"], 0.7),
                (mem_high["id"], 0.9),
            ]

        monkeypatch.setattr("megregore.embeddings.semantic_search", mock_search)

        from megregore.surfacing import surface_relevant
        results = await surface_relevant("test context")

        assert len(results) == 3
        scores = [r["_surfacing_score"] for r in results]
        assert scores == sorted(scores, reverse=True)
