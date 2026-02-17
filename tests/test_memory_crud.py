import pytest
import json

pytestmark = pytest.mark.asyncio


class TestUpdateMemory:
    async def test_update_content(self, mock_db, mock_embeddings, sample_memories):
        from megregore.memory import update_memory, get
        result = await update_memory(1, content="Updated content")
        assert result is not None
        assert result["content"] == "Updated content"
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
        from megregore.memory import update_memory, get
        original = await get(1)
        await update_memory(1, importance=3)
        mem = await get(1)
        assert mem["importance"] == 3
        assert mem["content"] == original["content"]

    async def test_update_nonexistent(self, mock_db, mock_embeddings):
        from megregore.memory import update_memory
        result = await update_memory(9999, content="nope")
        assert result is None


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
