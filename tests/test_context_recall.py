import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

pytestmark = pytest.mark.asyncio


class TestBlendContextScore:
    async def test_blend_with_session_relevance(self):
        from megregore.context_vector import blend_context_score
        # 0.7 * 0.5 + 0.3 * 1.0 = 0.35 + 0.30 = 0.65
        blended = blend_context_score(search_score=0.5, session_relevance=1.0)
        assert abs(blended - 0.65) < 0.01

    async def test_blend_with_zero_context(self):
        from megregore.context_vector import blend_context_score
        blended = blend_context_score(search_score=0.8, session_relevance=None)
        assert blended == 0.8

    async def test_blend_both_zero(self):
        from megregore.context_vector import blend_context_score
        blended = blend_context_score(search_score=0.0, session_relevance=0.0)
        assert blended == 0.0

    async def test_blend_both_one(self):
        from megregore.context_vector import blend_context_score
        blended = blend_context_score(search_score=1.0, session_relevance=1.0)
        assert abs(blended - 1.0) < 0.01


class TestCosineSimilarity:
    async def test_identical_vectors(self):
        from megregore.context_vector import cosine_similarity
        vec = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(vec, vec) - 1.0) < 0.001

    async def test_orthogonal_vectors(self):
        from megregore.context_vector import cosine_similarity
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(cosine_similarity(a, b)) < 0.001

    async def test_opposite_vectors(self):
        from megregore.context_vector import cosine_similarity
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 0.001

    async def test_zero_vector(self):
        from megregore.context_vector import cosine_similarity
        a = [0.0, 0.0]
        b = [1.0, 1.0]
        assert cosine_similarity(a, b) == 0.0


class TestComputeSessionContextVector:
    async def test_returns_none_when_no_memories(self, mock_db):
        from megregore.context_vector import compute_session_context_vector
        # Mock embeddings model as available
        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_model = AsyncMock(return_value=True)
            result = await compute_session_context_vector("no_session")
            assert result is None

    async def test_returns_none_when_model_unavailable(self, mock_db):
        from megregore.context_vector import compute_session_context_vector
        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_model = AsyncMock(return_value=False)
            result = await compute_session_context_vector("any_session")
            assert result is None


class TestSessionContextCache:
    async def test_cache_starts_empty(self):
        from megregore.context_vector import _session_context_cache
        # Clear any leftover state
        _session_context_cache.clear()
        assert len(_session_context_cache) == 0

    async def test_set_session_topic_populates_cache(self):
        from megregore.context_vector import set_session_topic, _session_context_cache
        _session_context_cache.clear()

        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_model = AsyncMock(return_value=True)

            fake_vec = [0.5] * 384
            mock_model = MagicMock()
            mock_model.encode.return_value = MagicMock(tolist=lambda: fake_vec)
            mock_emb._model = mock_model

            result = await set_session_topic(["consciousness", "philosophy"], session_id="topic_sess")
            assert result["status"] == "topic_set"
            assert "topic_sess" in _session_context_cache
            assert len(_session_context_cache["topic_sess"]) == 384

    async def test_set_session_topic_unavailable(self):
        from megregore.context_vector import set_session_topic
        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_model = AsyncMock(return_value=False)
            result = await set_session_topic(["test"], session_id="s1")
            assert result["status"] == "unavailable"


class TestGetContextScores:
    async def test_returns_empty_when_no_session_vector(self, mock_db):
        from megregore.context_vector import get_context_scores, _session_context_cache
        _session_context_cache.clear()
        with patch("megregore.context_vector.compute_session_context_vector", new_callable=AsyncMock, return_value=None):
            result = await get_context_scores([1, 2, 3], "no_vec_session")
            assert result == {}

    async def test_returns_empty_for_empty_candidates(self, mock_db):
        from megregore.context_vector import get_context_scores, _session_context_cache
        _session_context_cache["test_sess"] = [1.0, 0.0, 0.0]
        result = await get_context_scores([], "test_sess")
        assert result == {}
        _session_context_cache.clear()

    async def test_returns_scores_from_cache(self, mock_db):
        from megregore.context_vector import get_context_scores, _session_context_cache
        # Set up a cached session vector
        session_vec = [1.0, 0.0, 0.0]
        _session_context_cache["cached_sess"] = session_vec

        # Mock ChromaDB collection.get to return embeddings
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["1", "2"],
            "embeddings": [
                [1.0, 0.0, 0.0],  # Same as session vec → similarity ~1.0
                [0.0, 1.0, 0.0],  # Orthogonal → similarity ~0.0
            ],
        }

        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_collection = AsyncMock(return_value=mock_collection)
            result = await get_context_scores([1, 2], "cached_sess")

        assert abs(result[1] - 1.0) < 0.01  # Memory 1: high similarity
        assert abs(result[2] - 0.0) < 0.01  # Memory 2: orthogonal
        _session_context_cache.clear()

    async def test_clamps_negative_similarity(self, mock_db):
        from megregore.context_vector import get_context_scores, _session_context_cache
        session_vec = [1.0, 0.0]
        _session_context_cache["neg_sess"] = session_vec

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["5"],
            "embeddings": [[-1.0, 0.0]],  # Opposite → similarity = -1.0, clamped to 0
        }

        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_collection = AsyncMock(return_value=mock_collection)
            result = await get_context_scores([5], "neg_sess")

        assert result[5] == 0.0  # Clamped to 0
        _session_context_cache.clear()

    async def test_handles_chromadb_failure(self, mock_db):
        from megregore.context_vector import get_context_scores, _session_context_cache
        _session_context_cache["fail_sess"] = [1.0, 0.0]

        with patch("megregore.context_vector.embeddings") as mock_emb:
            mock_emb._ensure_collection = AsyncMock(return_value=None)
            result = await get_context_scores([1], "fail_sess")

        assert result == {}
        _session_context_cache.clear()
