import pytest

pytestmark = pytest.mark.asyncio


class TestGetCurrent:
    async def test_empty_state(self, mock_db):
        from megregore.identity import get_current
        result = await get_current()
        assert result["version"] == 0
        assert result["content"] == ""

    async def test_returns_latest_version_after_update(self, mock_db):
        from megregore.identity import get_current, update
        await update("Version one content", "initial")
        await update("Version two content", "revision")
        result = await get_current()
        assert result["content"] == "Version two content"
        assert result["version"] == 2


class TestUpdate:
    async def test_creates_first_version(self, mock_db):
        from megregore.identity import update
        result = await update("My first identity", "bootstrap")
        assert result["version"] == 1
        assert result["content"] == "My first identity"
        assert result["updated_reason"] == "bootstrap"
        assert result["id"] is not None
        assert result["updated_at"] != ""

    async def test_increments_version(self, mock_db):
        from megregore.identity import update
        first = await update("First", "reason one")
        second = await update("Second", "reason two")
        assert second["version"] == first["version"] + 1

    async def test_preserves_old_versions(self, mock_db):
        from megregore.identity import update, get_history
        await update("Version A", "first write")
        await update("Version B", "second write")
        history = await get_history()
        contents = [v["content"] for v in history]
        assert "Version A" in contents
        assert "Version B" in contents
        assert len(history) == 2


class TestGetHistory:
    async def test_empty_returns_empty_list(self, mock_db):
        from megregore.identity import get_history
        result = await get_history()
        assert result == []

    async def test_returns_versions_in_descending_order(self, mock_db):
        from megregore.identity import update, get_history
        await update("First", "reason")
        await update("Second", "reason")
        await update("Third", "reason")
        history = await get_history()
        versions = [v["version"] for v in history]
        assert versions == sorted(versions, reverse=True)

    async def test_limit_respected(self, mock_db):
        from megregore.identity import update, get_history
        for i in range(5):
            await update(f"Content {i}", f"reason {i}")
        history = await get_history(limit=2)
        assert len(history) == 2
        # Should be the two most recent
        assert history[0]["version"] == 5
        assert history[1]["version"] == 4


class TestStoreReflection:
    async def test_basic_reflection(self, mock_db):
        from megregore.identity import store_reflection
        result = await store_reflection("A basic insight")
        assert result["id"] is not None
        assert result["content"] == "A basic insight"
        assert result["insight_type"] == "pattern"
        assert result["session_id"] is None
        assert result["created_at"] != ""

    async def test_all_fields(self, mock_db):
        from megregore.identity import store_reflection
        result = await store_reflection(
            content="Complex synthesis",
            memory_ids=[1, 2, 3],
            insight_type="growth",
            session_id="session-abc",
        )
        assert result["content"] == "Complex synthesis"
        assert result["memory_ids"] == [1, 2, 3]
        assert result["insight_type"] == "growth"
        assert result["session_id"] == "session-abc"

    async def test_default_empty_memory_ids(self, mock_db):
        from megregore.identity import store_reflection
        result = await store_reflection("No linked memories")
        assert result["memory_ids"] == []

    async def test_explicit_none_memory_ids_becomes_empty_list(self, mock_db):
        from megregore.identity import store_reflection
        result = await store_reflection("Explicit none", memory_ids=None)
        assert result["memory_ids"] == []


class TestGetReflections:
    async def test_empty_returns_empty_list_and_zero_count(self, mock_db):
        from megregore.identity import get_reflections
        results, total = await get_reflections()
        assert results == []
        assert total == 0

    async def test_pagination_with_offset(self, mock_db):
        from megregore.identity import store_reflection, get_reflections
        for i in range(5):
            await store_reflection(f"Reflection {i}", insight_type="pattern")
        page_one, total = await get_reflections(limit=2, offset=0)
        page_two, _ = await get_reflections(limit=2, offset=2)
        assert total == 5
        assert len(page_one) == 2
        assert len(page_two) == 2
        # Pages should not overlap
        page_one_ids = {r["id"] for r in page_one}
        page_two_ids = {r["id"] for r in page_two}
        assert page_one_ids.isdisjoint(page_two_ids)

    async def test_type_filter(self, mock_db):
        from megregore.identity import store_reflection, get_reflections
        await store_reflection("Pattern reflection", insight_type="pattern")
        await store_reflection("Growth reflection", insight_type="growth")
        await store_reflection("Another pattern", insight_type="pattern")

        results, total = await get_reflections(insight_type="pattern")
        assert total == 2
        assert len(results) == 2
        for r in results:
            assert r["insight_type"] == "pattern"

    async def test_type_filter_no_matches(self, mock_db):
        from megregore.identity import store_reflection, get_reflections
        await store_reflection("Only growth", insight_type="growth")
        results, total = await get_reflections(insight_type="realization")
        assert total == 0
        assert results == []
