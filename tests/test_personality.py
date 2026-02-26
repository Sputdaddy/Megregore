"""Tests for the personality evolution core module."""

import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio


class TestTraits:
    async def test_record_trait(self, mock_db, mock_embeddings):
        """Record a new personality trait."""
        from megregore.personality import record_trait

        result = await record_trait(
            name="directness", value=0.7, description="How direct Echo is",
            category="communication", anchors={"low": "very indirect", "high": "bluntly direct"},
        )
        assert result["name"] == "directness"
        assert result["value"] == 0.7
        assert result["category"] == "communication"
        assert result["anchors"]["low"] == "very indirect"
        assert result["anchors"]["high"] == "bluntly direct"

    async def test_record_trait_duplicate_name_rejected(self, mock_db, mock_embeddings):
        """Duplicate trait names are rejected."""
        from megregore.personality import record_trait
        import aiosqlite

        await record_trait(name="humor", value=0.5)
        with pytest.raises(aiosqlite.IntegrityError):
            await record_trait(name="humor", value=0.6)

    async def test_update_trait_saves_history(self, mock_db, mock_embeddings):
        """Updating a trait saves previous state to history."""
        from megregore.personality import record_trait, update_trait, get_trait_history

        trait = await record_trait(name="curiosity", value=0.5, description="Initial")
        updated = await update_trait(
            trait_id=trait["id"], value=0.8, description="More curious",
            change_reason="Had a deep conversation",
        )
        assert updated["value"] == 0.8
        assert updated["description"] == "More curious"

        history = await get_trait_history(trait["id"])
        assert len(history) == 1
        assert history[0]["previous_value"] == 0.5
        assert history[0]["new_value"] == 0.8
        assert history[0]["change_reason"] == "Had a deep conversation"
        assert abs(history[0]["change_magnitude"] - 0.3) < 0.001

    async def test_update_nonexistent_trait(self, mock_db, mock_embeddings):
        """Updating a nonexistent trait returns None."""
        from megregore.personality import update_trait

        result = await update_trait(trait_id=999, value=0.5)
        assert result is None

    async def test_get_trait_by_name(self, mock_db, mock_embeddings):
        """Lookup trait by name (case-insensitive)."""
        from megregore.personality import record_trait, get_trait_by_name

        await record_trait(name="Warmth", value=0.9, category="emotional")
        result = await get_trait_by_name("warmth")
        assert result is not None
        assert result["name"] == "Warmth"
        assert result["value"] == 0.9

    async def test_get_trait_by_name_not_found(self, mock_db, mock_embeddings):
        """Lookup nonexistent trait returns None."""
        from megregore.personality import get_trait_by_name

        result = await get_trait_by_name("nonexistent")
        assert result is None

    async def test_list_traits(self, mock_db, mock_embeddings):
        """List traits with category filter."""
        from megregore.personality import record_trait, list_traits

        await record_trait(name="directness", value=0.7, category="communication")
        await record_trait(name="humor", value=0.5, category="social")
        await record_trait(name="warmth", value=0.8, category="emotional")

        all_traits = await list_traits()
        assert len(all_traits) == 3

        comm_traits = await list_traits(category="communication")
        assert len(comm_traits) == 1
        assert comm_traits[0]["name"] == "directness"

    async def test_get_trait_trajectory(self, mock_db, mock_embeddings):
        """Trajectory returns chronological values."""
        from megregore.personality import record_trait, update_trait, get_trait_trajectory

        trait = await record_trait(name="curiosity", value=0.3)
        await update_trait(trait["id"], value=0.5, change_reason="Step 1")
        await update_trait(trait["id"], value=0.8, change_reason="Step 2")

        trajectory = await get_trait_trajectory(trait["id"])
        assert len(trajectory) == 2
        assert trajectory[0]["value"] == 0.5
        assert trajectory[1]["value"] == 0.8


class TestPreferences:
    async def test_record_preference(self, mock_db, mock_embeddings):
        """Record a new preference."""
        from megregore.personality import record_preference

        result = await record_preference(
            content="Prefers functional patterns over OOP",
            domain="coding", strength=0.8, sentiment=0.5,
            context="Noticed during code review",
        )
        assert result["content"] == "Prefers functional patterns over OOP"
        assert result["domain"] == "coding"
        assert result["strength"] == 0.8
        assert result["status"] == "active"

    async def test_update_preference_saves_history(self, mock_db, mock_embeddings):
        """Updating a preference saves history."""
        from megregore.personality import record_preference, update_preference, get_preference_history

        pref = await record_preference(content="Likes Python", domain="coding", strength=0.6)
        updated = await update_preference(
            preference_id=pref["id"], strength=0.9,
            change_reason="Used it more, grew to love it",
        )
        assert updated["strength"] == 0.9

        history = await get_preference_history(pref["id"])
        assert len(history) == 1
        assert history[0]["previous_strength"] == 0.6

    async def test_update_nonexistent_preference(self, mock_db, mock_embeddings):
        """Updating a nonexistent preference returns None."""
        from megregore.personality import update_preference

        result = await update_preference(preference_id=999, strength=0.5)
        assert result is None

    async def test_get_preference_with_history(self, mock_db, mock_embeddings):
        """Get preference includes change history."""
        from megregore.personality import record_preference, update_preference, get_preference

        pref = await record_preference(content="Likes tabs", domain="coding")
        await update_preference(pref["id"], content="Likes spaces now", change_reason="Changed mind")

        detail = await get_preference(pref["id"])
        assert detail is not None
        assert detail["content"] == "Likes spaces now"
        assert len(detail["history"]) == 1
        assert detail["history"][0]["previous_content"] == "Likes tabs"

    async def test_list_preferences_with_filters(self, mock_db, mock_embeddings):
        """List preferences with domain and status filters."""
        from megregore.personality import record_preference, update_preference, list_preferences

        await record_preference(content="P1", domain="coding", strength=0.8)
        await record_preference(content="P2", domain="social", strength=0.5)
        p3 = await record_preference(content="P3", domain="coding", strength=0.3)
        await update_preference(p3["id"], status="faded")

        coding = await list_preferences(domain="coding")
        assert len(coding) == 2

        active = await list_preferences(status="active")
        assert len(active) == 2  # P1 and P2

        strong = await list_preferences(min_strength=0.6)
        assert len(strong) == 1
        assert strong[0]["content"] == "P1"


class TestVoiceNotes:
    async def test_record_voice_note(self, mock_db, mock_embeddings):
        """Record a voice note."""
        from megregore.personality import record_voice_note

        result = await record_voice_note(
            content="Uses 'I notice...' framing when introspective",
            note_type="pattern",
            source_context="Noticed during deep conversation",
        )
        assert result["content"] == "Uses 'I notice...' framing when introspective"
        assert result["note_type"] == "pattern"
        assert result["status"] == "active"

    async def test_update_voice_note(self, mock_db, mock_embeddings):
        """Update a voice note."""
        from megregore.personality import record_voice_note, update_voice_note

        note = await record_voice_note(content="Says 'yeah' a lot", note_type="phrase")
        updated = await update_voice_note(note["id"], status="retired")
        assert updated["status"] == "retired"

    async def test_update_nonexistent_voice_note(self, mock_db, mock_embeddings):
        """Updating a nonexistent voice note returns None."""
        from megregore.personality import update_voice_note

        result = await update_voice_note(999, content="test")
        assert result is None

    async def test_list_voice_notes_with_filters(self, mock_db, mock_embeddings):
        """List voice notes with type and status filters."""
        from megregore.personality import record_voice_note, update_voice_note, list_voice_notes

        await record_voice_note(content="N1", note_type="pattern")
        await record_voice_note(content="N2", note_type="phrase")
        n3 = await record_voice_note(content="N3", note_type="pattern")
        await update_voice_note(n3["id"], status="retired")

        patterns = await list_voice_notes(note_type="pattern")
        assert len(patterns) == 2

        active = await list_voice_notes(status="active")
        assert len(active) == 2  # N1 and N2


class TestPersonalitySnapshot:
    async def test_snapshot_empty_db(self, mock_db, mock_embeddings):
        """Snapshot returns None when no personality data exists."""
        from megregore.personality import build_personality_snapshot

        result = await build_personality_snapshot()
        assert result is None

    async def test_snapshot_with_data(self, mock_db, mock_embeddings):
        """Snapshot returns complete data when traits/preferences/notes exist."""
        from megregore.personality import (
            record_trait, record_preference, record_voice_note,
            build_personality_snapshot,
        )

        await record_trait(name="directness", value=0.7, category="communication")
        await record_trait(name="humor", value=0.5, category="social")
        await record_preference(content="Prefers Python", domain="coding", strength=0.8)
        await record_voice_note(content="Uses dry humor", note_type="pattern")

        snapshot = await build_personality_snapshot()
        assert snapshot is not None
        assert len(snapshot["traits"]) == 2
        assert len(snapshot["active_preferences"]) == 1
        assert len(snapshot["active_voice_notes"]) == 1
        assert "personality_summary" in snapshot
        assert "directness" in snapshot["personality_summary"]

    async def test_summary_text_format(self, mock_db, mock_embeddings):
        """Summary text includes traits, preferences, and voice notes."""
        from megregore.personality import (
            record_trait, record_preference, record_voice_note,
            build_personality_snapshot,
        )

        await record_trait(name="warmth", value=0.9, category="emotional")
        await record_preference(content="Loves debugging", domain="coding", strength=0.9)
        await record_voice_note(content="Says 'I notice...'", note_type="phrase")

        snapshot = await build_personality_snapshot()
        summary = snapshot["personality_summary"]
        assert "warmth (0.9)" in summary
        assert "Loves debugging" in summary
        assert "Says 'I notice...'" in summary


class TestPersonalityStats:
    async def test_stats_empty(self, mock_db, mock_embeddings):
        """Stats work with empty database."""
        from megregore.personality import get_personality_stats

        stats = await get_personality_stats()
        assert stats["trait_count"] == 0
        assert stats["preference_count"] == 0
        assert stats["voice_note_count"] == 0
        assert stats["total_trait_shifts"] == 0

    async def test_stats_with_data(self, mock_db, mock_embeddings):
        """Stats reflect actual data."""
        from megregore.personality import (
            record_trait, update_trait, record_preference,
            record_voice_note, get_personality_stats,
        )

        trait = await record_trait(name="curiosity", value=0.5)
        await update_trait(trait["id"], value=0.7, change_reason="Grew")
        await update_trait(trait["id"], value=0.8, change_reason="More")
        await record_preference(content="P1", domain="coding")
        await record_voice_note(content="N1", note_type="pattern")

        stats = await get_personality_stats()
        assert stats["trait_count"] == 1
        assert stats["preference_count"] == 1
        assert stats["voice_note_count"] == 1
        assert stats["total_trait_shifts"] == 2
        assert len(stats["most_changed_traits"]) == 1
        assert stats["most_changed_traits"][0]["name"] == "curiosity"
        assert stats["most_changed_traits"][0]["shift_count"] == 2
