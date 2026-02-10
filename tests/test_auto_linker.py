import pytest
from megregore.auto_linker import infer_links, suggest_links, _find_unlinked_pairs

pytestmark = pytest.mark.asyncio


class TestInferLinks:
    async def test_returns_stats(self, mock_db, mock_embeddings, sample_memories):
        result = await infer_links()
        assert "status" in result
        assert "scanned" in result
        assert "created" in result
        assert "skipped_existing" in result

    async def test_empty_database(self, mock_db, mock_embeddings):
        result = await infer_links()
        assert result["created"] == 0

    async def test_respects_max_links(self, mock_db, mock_embeddings, sample_memories, monkeypatch):
        async def mock_search(query, limit=20):
            return [(1, 0.95), (2, 0.90), (3, 0.88)]
        monkeypatch.setattr("megregore.embeddings.semantic_search", mock_search)

        result = await infer_links(max_new_links=1)
        assert result["created"] <= 1


class TestSuggestLinks:
    async def test_returns_suggestions(self, mock_db, mock_embeddings, sample_memories):
        suggestions = await suggest_links(limit=5)
        assert isinstance(suggestions, list)

    async def test_empty_database(self, mock_db, mock_embeddings):
        suggestions = await suggest_links()
        assert suggestions == []
