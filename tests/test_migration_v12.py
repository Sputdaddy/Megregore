"""Tests for the v11 -> v12 migration (personality evolution tables)."""

import pytest
import aiosqlite

pytestmark = pytest.mark.asyncio


class TestMigrationV12:
    async def test_tables_created(self, db):
        """All v12 tables exist after migration."""
        tables = ["personality_traits", "trait_history", "preferences", "preference_history", "voice_notes"]
        for table in tables:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            row = await cursor.fetchone()
            assert row is not None, f"Table {table} not found"

    async def test_indexes_created(self, db):
        """Key indexes exist after migration."""
        expected = [
            "idx_personality_traits_category",
            "idx_personality_traits_updated",
            "idx_trait_history_trait_created",
            "idx_preferences_domain",
            "idx_preferences_status",
            "idx_preferences_strength",
            "idx_preferences_updated",
            "idx_preference_history_pref_created",
            "idx_voice_notes_type",
            "idx_voice_notes_status",
            "idx_voice_notes_updated",
        ]
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        all_indexes = {row[0] for row in await cursor.fetchall()}
        for idx in expected:
            assert idx in all_indexes, f"Index {idx} not found"

    async def test_schema_version_bumped(self, db):
        """Schema version is 12 after migration."""
        cursor = await db.execute(
            "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert int(row[0]) == 12

    async def test_idempotent(self, db):
        """Running migration twice doesn't error."""
        from megregore.migrations import migrate_v11_to_v12
        result = await migrate_v11_to_v12(db)
        assert result["status"] == "already_migrated"
        assert result["from_version"] == 12

    async def test_personality_traits_constraints(self, db):
        """Personality traits table has correct constraints."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Insert a valid trait
        await db.execute(
            "INSERT INTO personality_traits (name, category, value, description, anchors, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("directness", "communication", 0.7, "How direct Echo is", '{}', now, now),
        )
        await db.commit()

        # Duplicate name should fail
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO personality_traits (name, category, value, description, anchors, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("directness", "general", 0.5, "duplicate", '{}', now, now),
            )

    async def test_trait_history_foreign_key(self, db):
        """Trait history references personality_traits."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "INSERT INTO personality_traits (name, category, value, description, anchors, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("humor", "social", 0.5, "Humor style", '{}', now, now),
        )
        cursor = await db.execute("SELECT last_insert_rowid()")
        trait_id = (await cursor.fetchone())[0]

        await db.execute(
            """INSERT INTO trait_history (trait_id, previous_value, new_value, change_reason, change_magnitude, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (trait_id, 0.5, 0.7, "Got funnier", 0.2, now),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM trait_history WHERE trait_id = ?", (trait_id,))
        row = await cursor.fetchone()
        assert row is not None

    async def test_preferences_value_constraints(self, db):
        """Preferences respect value constraints."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Valid insert
        await db.execute(
            "INSERT INTO preferences (content, domain, strength, sentiment, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Prefers functional patterns", "coding", 0.8, 0.5, "active", now, now),
        )
        await db.commit()

        # Out-of-range strength should fail
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO preferences (content, domain, strength, sentiment, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("Bad", "general", 1.5, 0.0, "active", now, now),
            )
