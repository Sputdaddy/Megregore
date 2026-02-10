import pytest
from megregore.threads import create_thread, assign_to_thread, list_threads, get_thread

pytestmark = pytest.mark.asyncio


class TestCreateThread:
    async def test_basic_creation(self, mock_db):
        thread = await create_thread("Test Topic", "A test thread")
        assert thread["id"] is not None
        assert thread["title"] == "Test Topic"
        assert thread["memory_count"] == 0


class TestAssignToThread:
    async def test_assign_memory(self, mock_db, mock_embeddings):
        from megregore.memory import store
        thread = await create_thread("Topic")
        memory = await store(content="Test", session_id="s1")
        result = await assign_to_thread(memory["id"], thread["id"])
        assert result is True


class TestListThreads:
    async def test_list_empty(self, mock_db):
        threads, total = await list_threads()
        assert total == 0
        assert threads == []

    async def test_list_with_threads(self, mock_db):
        await create_thread("Thread 1")
        await create_thread("Thread 2")
        threads, total = await list_threads()
        assert total == 2
