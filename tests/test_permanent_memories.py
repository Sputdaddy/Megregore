"""Tests for the permanent memories feature (V11 migration)."""

import pytest
import json
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio


class TestMigrationV11:
    async def test_migration_adds_column(self, db):
        """Verify the is_permanent column exists after migration."""
        cursor = await db.execute("PRAGMA table_info(memories)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "is_permanent" in columns

    async def test_migration_default_value(self, db):
        """Existing memories should default to is_permanent=0."""
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source, created_at, last_accessed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("test", "fact", 5, 0.0, "[]", "test", now, now),
        )
        await db.commit()
        cursor = await db.execute("SELECT is_permanent FROM memories WHERE content = 'test'")
        row = await cursor.fetchone()
        assert row[0] == 0

    async def test_migration_idempotent(self, db):
        """Running migration twice should not error."""
        from megregore.migrations import migrate_v10_to_v11
        result = await migrate_v10_to_v11(db)
        assert result["status"] == "already_migrated"


class TestStoreWithPermanent:
    async def test_store_permanent_memory(self, mock_db, mock_embeddings):
        from megregore.memory import store, get
        mem = await store(content="Always remember this", importance=9, is_permanent=True)
        assert mem["is_permanent"] == 1
        fetched = await get(mem["id"])
        assert fetched["is_permanent"] == 1

    async def test_store_default_not_permanent(self, mock_db, mock_embeddings):
        from megregore.memory import store, get
        mem = await store(content="Normal memory")
        assert mem["is_permanent"] == 0
        fetched = await get(mem["id"])
        assert fetched["is_permanent"] == 0


class TestDecayExemption:
    async def test_permanent_memory_excluded_from_decay(self, mock_db, mock_embeddings):
        """Permanent memories should not be touched by activation decay."""
        from megregore.memory import store, apply_activation_decay, get

        perm = await store(content="Permanent fact", importance=9, is_permanent=True)
        normal = await store(content="Normal memory", importance=3, is_permanent=False)

        result = await apply_activation_decay()
        # The permanent memory should not be in the updated count (or at least unmodified)
        perm_after = await get(perm["id"])
        assert perm_after["activation_level"] == 1.0  # Never decayed


class TestFadeGuard:
    async def test_fade_permanent_memory_blocked(self, mock_db, mock_embeddings):
        """Fading a permanent memory should return an error, not reduce importance."""
        from megregore.memory import store, fade

        mem = await store(content="Protected", importance=9, is_permanent=True)
        result = await fade(mem["id"], amount=0.5)
        assert result is not None
        assert result.get("_error") is not None
        assert "permanent" in result["_error"].lower()
        # Importance should be unchanged
        assert result["importance"] == 9

    async def test_fade_normal_memory_works(self, mock_db, mock_embeddings):
        """Normal memories can still be faded."""
        from megregore.memory import store, fade

        mem = await store(content="Normal", importance=8, is_permanent=False)
        result = await fade(mem["id"], amount=0.5)
        assert result is not None
        assert "_error" not in result
        assert result["importance"] < 8


class TestConsolidationGuard:
    async def test_consolidation_skips_fading_permanent_source(self, mock_db, mock_embeddings):
        """Permanent source memories should not be faded during consolidation."""
        from megregore.memory import store, consolidate_memories, get

        perm = await store(content="Permanent source", importance=9, is_permanent=True)
        normal = await store(content="Normal source", importance=7, is_permanent=False)

        result = await consolidate_memories(
            source_ids=[perm["id"], normal["id"]],
            synthesis="Combined insight",
            importance=8,
            fade_amount=0.5,
        )
        assert result["status"] == "consolidated"
        assert result["faded_count"] == 1  # Only normal was faded

        # Permanent source should keep original importance
        perm_after = await get(perm["id"])
        assert perm_after["importance"] == 9

        # Normal source should be faded
        normal_after = await get(normal["id"])
        assert normal_after["importance"] < 7


class TestPinUnpin:
    async def test_pin_memory(self, mock_db, mock_embeddings):
        from megregore.memory import store, update_memory, get

        mem = await store(content="Pin me", importance=5)
        assert mem["is_permanent"] == 0

        await update_memory(mem["id"], is_permanent=True)
        fetched = await get(mem["id"])
        assert fetched["is_permanent"] == 1

    async def test_unpin_memory(self, mock_db, mock_embeddings):
        from megregore.memory import store, update_memory, get

        mem = await store(content="Unpin me", importance=5, is_permanent=True)
        assert mem["is_permanent"] == 1

        await update_memory(mem["id"], is_permanent=False)
        fetched = await get(mem["id"])
        assert fetched["is_permanent"] == 0


class TestGetAllFilter:
    async def test_filter_permanent_only(self, mock_db, mock_embeddings):
        from megregore.memory import store, get_all

        await store(content="Normal 1", importance=5)
        await store(content="Permanent 1", importance=8, is_permanent=True)
        await store(content="Normal 2", importance=4)

        memories, total = await get_all(is_permanent=True)
        assert total == 1
        assert memories[0]["content"] == "Permanent 1"

    async def test_filter_non_permanent(self, mock_db, mock_embeddings):
        from megregore.memory import store, get_all

        await store(content="Normal 1", importance=5)
        await store(content="Permanent 1", importance=8, is_permanent=True)

        memories, total = await get_all(is_permanent=False)
        assert total == 1
        assert memories[0]["content"] == "Normal 1"

    async def test_no_filter_returns_all(self, mock_db, mock_embeddings):
        from megregore.memory import store, get_all

        await store(content="Normal 1", importance=5)
        await store(content="Permanent 1", importance=8, is_permanent=True)

        memories, total = await get_all()
        assert total == 2


class TestSessionStartup:
    async def test_permanent_memories_in_session_start(self, mock_db, mock_embeddings):
        """Permanent memories should appear in session_start under permanent_memories key."""
        from megregore.memory import store, create_session
        from megregore.session_startup import build_session_start

        await create_session("test-session")
        await store(content="Always loaded fact", importance=9, is_permanent=True)
        await store(content="Normal memory", importance=5)

        result = await build_session_start("test-session")

        assert "permanent_memories" in result
        assert result["permanent_count"] == 1
        assert result["permanent_memories"][0]["content"] == "Always loaded fact"

    async def test_permanent_memories_deduplicated_from_regular(self, mock_db, mock_embeddings):
        """A permanent memory should not also appear in the regular memories list."""
        from megregore.memory import store, create_session
        from megregore.session_startup import build_session_start

        await create_session("test-session")
        # Store a high-importance permanent memory that would also match regular recall
        await store(
            content="Important permanent fact",
            importance=10,
            is_permanent=True,
            tags=["important"],
        )

        result = await build_session_start("test-session")

        perm_ids = {m["id"] for m in result["permanent_memories"]}
        regular_ids = {m["id"] for m in result["memories"]}
        # No overlap
        assert perm_ids.isdisjoint(regular_ids)

    async def test_permanent_memories_truncated_at_300(self, mock_db, mock_embeddings):
        """Permanent memories should truncate at 300 chars, not 200."""
        from megregore.memory import store, create_session
        from megregore.session_startup import build_session_start

        await create_session("test-session")
        long_content = "x" * 400
        await store(content=long_content, importance=9, is_permanent=True)

        result = await build_session_start("test-session")
        content = result["permanent_memories"][0]["content"]
        # Should be truncated at 300 + "..."
        assert len(content) == 303
        assert content.endswith("...")

    async def test_permanent_memories_limit_20(self, mock_db, mock_embeddings):
        """At most 20 permanent memories should be returned."""
        from megregore.memory import store, create_session
        from megregore.session_startup import build_session_start

        await create_session("test-session")
        for i in range(25):
            await store(content=f"Permanent {i}", importance=5, is_permanent=True)

        result = await build_session_start("test-session")
        assert result["permanent_count"] <= 20
