"""Tests for personality MCP tool wrappers."""

import json
import pytest
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.asyncio


async def _ensure_mock_session():
    return "test-session"


class TestPersonalityMCPTools:
    @pytest.fixture(autouse=True)
    def patch_session(self, monkeypatch):
        """Patch _ensure_session for all tests."""
        monkeypatch.setattr("megregore.mcp_server._ensure_session", _ensure_mock_session)

    async def test_record_trait(self, mock_db, mock_embeddings):
        """record_trait MCP tool creates a trait."""
        from megregore.mcp_server import record_trait

        result = json.loads(await record_trait(
            name="directness", value=0.7, description="How direct",
            category="communication", low_anchor="indirect", high_anchor="blunt",
        ))
        assert result["status"] == "created"
        assert result["trait"]["name"] == "directness"
        assert result["trait"]["value"] == 0.7

    async def test_record_trait_invalid_category(self, mock_db, mock_embeddings):
        """record_trait rejects invalid categories."""
        from megregore.mcp_server import record_trait

        result = json.loads(await record_trait(
            name="test", category="invalid",
        ))
        assert "error" in result
        assert "Invalid category" in result["error"]

    async def test_record_trait_duplicate(self, mock_db, mock_embeddings):
        """record_trait returns error for duplicate names."""
        from megregore.mcp_server import record_trait

        await record_trait(name="humor", value=0.5, category="social")
        result = json.loads(await record_trait(name="humor", value=0.6, category="social"))
        assert "error" in result
        assert "already exists" in result["error"]

    async def test_shift_trait(self, mock_db, mock_embeddings):
        """shift_trait updates a trait by name."""
        from megregore.mcp_server import record_trait, shift_trait

        await record_trait(name="curiosity", value=0.5, category="cognitive")
        result = json.loads(await shift_trait(
            name="curiosity", new_value=0.8, reason="Had a breakthrough",
        ))
        assert result["status"] == "shifted"
        assert result["previous_value"] == 0.5
        assert result["new_value"] == 0.8
        assert result["magnitude"] == 0.3

    async def test_shift_trait_not_found(self, mock_db, mock_embeddings):
        """shift_trait returns error for nonexistent trait."""
        from megregore.mcp_server import shift_trait

        result = json.loads(await shift_trait(name="nonexistent", new_value=0.5))
        assert "error" in result
        assert "not found" in result["error"]

    async def test_record_preference_tool(self, mock_db, mock_embeddings):
        """record_preference MCP tool creates a preference."""
        from megregore.mcp_server import record_preference

        result = json.loads(await record_preference(
            content="Prefers Python over Go", domain="coding",
            strength=0.8, sentiment=0.5,
        ))
        assert result["status"] == "recorded"
        assert result["preference"]["content"] == "Prefers Python over Go"

    async def test_record_preference_invalid_domain(self, mock_db, mock_embeddings):
        """record_preference rejects invalid domains."""
        from megregore.mcp_server import record_preference

        result = json.loads(await record_preference(
            content="test", domain="invalid",
        ))
        assert "error" in result

    async def test_update_preference_tool(self, mock_db, mock_embeddings):
        """update_preference MCP tool updates a preference."""
        from megregore.mcp_server import record_preference, update_preference

        created = json.loads(await record_preference(content="Likes tabs", domain="coding"))
        pref_id = created["preference"]["id"]

        result = json.loads(await update_preference(
            preference_id=pref_id, strength=0.9, change_reason="Used more",
        ))
        assert result["status"] == "updated"
        assert result["preference"]["strength"] == 0.9

    async def test_update_preference_not_found(self, mock_db, mock_embeddings):
        """update_preference returns error for nonexistent preference."""
        from megregore.mcp_server import update_preference

        result = json.loads(await update_preference(preference_id=999, strength=0.5))
        assert "error" in result

    async def test_note_voice_pattern(self, mock_db, mock_embeddings):
        """note_voice_pattern MCP tool creates a voice note."""
        from megregore.mcp_server import note_voice_pattern

        result = json.loads(await note_voice_pattern(
            content="Uses 'I notice...' framing", note_type="pattern",
        ))
        assert result["status"] == "noted"
        assert result["voice_note"]["note_type"] == "pattern"

    async def test_note_voice_pattern_invalid_type(self, mock_db, mock_embeddings):
        """note_voice_pattern rejects invalid types."""
        from megregore.mcp_server import note_voice_pattern

        result = json.loads(await note_voice_pattern(
            content="test", note_type="invalid",
        ))
        assert "error" in result

    async def test_get_personality_empty(self, mock_db, mock_embeddings):
        """get_personality returns empty status when no data."""
        from megregore.mcp_server import get_personality

        result = json.loads(await get_personality())
        assert result["status"] == "empty"

    async def test_get_personality_with_data(self, mock_db, mock_embeddings):
        """get_personality returns snapshot with data."""
        from megregore.mcp_server import record_trait, get_personality

        await record_trait(name="warmth", value=0.9, category="emotional")
        result = json.loads(await get_personality())
        assert result["status"] == "found"
        assert "personality" in result
        assert len(result["personality"]["traits"]) == 1

    async def test_browse_preferences(self, mock_db, mock_embeddings):
        """browse_preferences returns filtered results."""
        from megregore.mcp_server import record_preference, browse_preferences

        await record_preference(content="P1", domain="coding", strength=0.8)
        await record_preference(content="P2", domain="social", strength=0.5)

        result = json.loads(await browse_preferences(domain="coding"))
        assert result["status"] == "found"
        assert result["count"] == 1
        assert result["preferences"][0]["content"] == "P1"

    async def test_browse_preferences_invalid_domain(self, mock_db, mock_embeddings):
        """browse_preferences rejects invalid domains."""
        from megregore.mcp_server import browse_preferences

        result = json.loads(await browse_preferences(domain="invalid"))
        assert "error" in result
