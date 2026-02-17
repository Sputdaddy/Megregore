import pytest
import aiosqlite

pytestmark = pytest.mark.asyncio


class TestMigrationV9ToV10:
    async def test_creates_session_summaries_table(self, db):
        """Migration should create session_summaries table."""
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_summaries'"
        )
        row = await cursor.fetchone()
        assert row is not None, "session_summaries table should exist"

    async def test_session_summaries_columns(self, db):
        """Table should have all expected columns."""
        cursor = await db.execute("PRAGMA table_info(session_summaries)")
        columns = {row[1] for row in await cursor.fetchall()}
        expected = {"id", "session_id", "topics", "decisions", "next_steps", "mood", "files_changed", "created_at"}
        assert expected == columns

    async def test_index_exists(self, db):
        """Index on session_id should exist."""
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_session_summaries_session'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_schema_version_bumped(self, db):
        """Schema version should be 10."""
        cursor = await db.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        )
        row = await cursor.fetchone()
        assert row[0] == "10"

    async def test_idempotent(self, db):
        """Running migration twice should be safe."""
        from megregore.migrations import migrate_v9_to_v10
        result = await migrate_v9_to_v10(db)
        assert result["status"] == "already_migrated"
