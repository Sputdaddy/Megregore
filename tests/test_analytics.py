import pytest
from megregore.analytics import log_access, get_top_accessed, compute_analytics

pytestmark = pytest.mark.asyncio


class TestLogAccess:
    async def test_basic_log(self, mock_db, mock_embeddings, sample_memories):
        await log_access(1, "recall", session_id="test-session")


class TestComputeAnalytics:
    async def test_empty_database(self, mock_db, mock_embeddings):
        stats = await compute_analytics()
        assert stats["total_memories"] == 0
        assert stats["total_accesses"] == 0

    async def test_with_data(self, mock_db, mock_embeddings, sample_memories):
        stats = await compute_analytics()
        assert stats["total_memories"] == 7


class TestGetTopAccessed:
    async def test_empty_period(self, mock_db, mock_embeddings, sample_memories):
        result = await get_top_accessed(days=1)
        assert isinstance(result, list)
