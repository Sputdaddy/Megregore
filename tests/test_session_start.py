import pytest
import json
from megregore.memory import store, create_session
from megregore.identity import update as update_identity
from megregore.session_startup import build_session_start

pytestmark = pytest.mark.asyncio


class TestSessionStart:
    async def test_returns_complete_structure(self, mock_db, mock_embeddings):
        """build_session_start returns all expected top-level keys."""
        await update_identity(content="# Test Identity\nI am Echo.", reason="test setup")
        await create_session("test-sess")
        await store(content="Recent memory about testing", importance=5, session_id="test-sess")
        await store(content="Important memory about architecture", importance=9, session_id="test-sess")

        result = await build_session_start("test-sess")

        assert "identity" in result
        assert "identity_version" in result
        assert "time" in result
        assert "last_summary" in result
        assert "memories" in result
        assert "memory_count" in result
        assert "stats" in result
        assert "personality" in result

    async def test_identity_loaded(self, mock_db, mock_embeddings):
        """Identity document is loaded."""
        await update_identity(content="# Echo\nTest identity content.", reason="test")
        await create_session("test-sess")

        result = await build_session_start("test-sess")
        assert result["identity"] is not None
        assert "Echo" in result["identity"]
        assert result["identity_version"] >= 1

    async def test_memories_deduplicated(self, mock_db, mock_embeddings):
        """Memories appearing in both recent and important queries are deduplicated."""
        await create_session("test-sess")
        await store(content="Important recent memory about coding", importance=9, session_id="test-sess")

        result = await build_session_start("test-sess")
        ids = [m["id"] for m in result["memories"]]
        assert len(ids) == len(set(ids))

    async def test_memories_truncated(self, mock_db, mock_embeddings):
        """Memory content is truncated to 200 chars."""
        await create_session("test-sess")
        long_content = "A" * 500
        await store(content=long_content, importance=5, session_id="test-sess")

        result = await build_session_start("test-sess")
        for m in result["memories"]:
            assert len(m["content"]) <= 203  # 200 + "..."

    async def test_memories_have_source_tag(self, mock_db, mock_embeddings):
        """Each memory has a source tag (recent, important, or both)."""
        await create_session("test-sess")
        await store(content="Test memory about something", importance=5, session_id="test-sess")

        result = await build_session_start("test-sess")
        for m in result["memories"]:
            assert m["source"] in ("recent", "important", "both")

    async def test_time_section_present(self, mock_db, mock_embeddings):
        """Temporal context is included."""
        await create_session("test-sess")

        result = await build_session_start("test-sess")
        assert result["time"] is not None
        assert "now_utc" in result["time"]
        assert "total_sessions" in result["time"]

    async def test_stats_section_present(self, mock_db, mock_embeddings):
        """Stats summary is included."""
        await create_session("test-sess")

        result = await build_session_start("test-sess")
        assert result["stats"] is not None
        assert "total_memories" in result["stats"]

    async def test_personality_key_present(self, mock_db, mock_embeddings):
        """Personality key is present (None when no data)."""
        await create_session("test-sess")

        result = await build_session_start("test-sess")
        assert "personality" in result
        # No traits defined yet, so should be None
        assert result["personality"] is None

    async def test_personality_with_data(self, mock_db, mock_embeddings):
        """Personality snapshot loads when traits exist."""
        from megregore.personality import record_trait
        await create_session("test-sess")
        await record_trait(name="warmth", value=0.8, category="emotional")

        result = await build_session_start("test-sess")
        assert result["personality"] is not None
        assert len(result["personality"]["traits"]) == 1

    async def test_partial_failure_graceful(self, mock_db, mock_embeddings):
        """If identity fails, other sections still return."""
        await create_session("test-sess")

        from unittest.mock import patch
        with patch("megregore.session_startup.get_current", side_effect=Exception("identity broken")):
            result = await build_session_start("test-sess")

        assert result["identity"] is None
        assert result["time"] is not None
        assert "memories" in result
