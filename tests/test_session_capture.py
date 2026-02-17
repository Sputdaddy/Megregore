import pytest
import json

pytestmark = pytest.mark.asyncio


class TestSnapshotContext:
    async def test_creates_memory(self, mock_db, mock_embeddings):
        from megregore.session_capture import snapshot_context

        result = await snapshot_context(
            content="We were debugging the pathfinding system",
            session_id="test1234",
        )
        assert result["status"] == "captured"
        assert result["memory_id"] > 0

    async def test_defaults(self, mock_db, mock_embeddings):
        from megregore.session_capture import snapshot_context

        result = await snapshot_context(
            content="Quick context save",
            session_id="test1234",
        )
        from megregore.memory import get

        mem = await get(result["memory_id"])
        assert mem["importance"] == 7
        assert mem["memory_type"] == "experience"
        assert "context-snapshot" in mem["tags"]

    async def test_custom_tags(self, mock_db, mock_embeddings):
        from megregore.session_capture import snapshot_context

        result = await snapshot_context(
            content="Saving with custom tags",
            tags=["megregore", "v11"],
            session_id="test1234",
        )
        from megregore.memory import get

        mem = await get(result["memory_id"])
        assert "context-snapshot" in mem["tags"]
        assert "megregore" in mem["tags"]
        assert "v11" in mem["tags"]


class TestSessionSummary:
    async def test_creates_summary_record(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary

        result = await create_session_summary(
            topics=["pathfinding", "TCP connections"],
            session_id="test1234",
        )
        assert result["status"] == "summarized"
        assert result["summary_id"] > 0

    async def test_stores_all_fields(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary
        from megregore import database

        result = await create_session_summary(
            topics=["megregore", "v11"],
            decisions=["use SSE for events", "hard delete for memories"],
            next_steps=["implement events.py", "add mobile CSS"],
            mood="productive",
            files_changed=["memory.py", "mcp_server.py"],
            session_id="test1234",
        )
        db = await database.get_connection()
        cursor = await db.execute(
            "SELECT * FROM session_summaries WHERE id = ?", (result["summary_id"],)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert json.loads(row["topics"]) == ["megregore", "v11"]
        assert json.loads(row["decisions"]) == [
            "use SSE for events",
            "hard delete for memories",
        ]
        assert json.loads(row["next_steps"]) == [
            "implement events.py",
            "add mobile CSS",
        ]
        assert row["mood"] == "productive"
        assert json.loads(row["files_changed"]) == ["memory.py", "mcp_server.py"]

    async def test_also_creates_memory(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary

        result = await create_session_summary(
            topics=["testing"],
            session_id="test1234",
        )
        assert result["memory_id"] > 0

    async def test_defaults(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary
        from megregore import database

        result = await create_session_summary(
            topics=["quick test"],
            session_id="test1234",
        )
        db = await database.get_connection()
        cursor = await db.execute(
            "SELECT * FROM session_summaries WHERE id = ?", (result["summary_id"],)
        )
        row = await cursor.fetchone()
        assert json.loads(row["decisions"]) == []
        assert json.loads(row["next_steps"]) == []
        assert row["mood"] == "productive"


class TestGetLastSummary:
    async def test_returns_none_when_empty(self, mock_db):
        from megregore.session_capture import get_last_summary

        result = await get_last_summary()
        assert result is None

    async def test_returns_latest(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary, get_last_summary

        await create_session_summary(topics=["first"], session_id="sess1")
        await create_session_summary(topics=["second"], session_id="sess2")
        result = await get_last_summary()
        assert result is not None
        assert json.loads(result["topics"]) == ["second"]

    async def test_excludes_current_session(self, mock_db, mock_embeddings):
        from megregore.session_capture import create_session_summary, get_last_summary

        await create_session_summary(topics=["old"], session_id="sess1")
        await create_session_summary(topics=["current"], session_id="sess2")
        result = await get_last_summary(exclude_session="sess2")
        assert result is not None
        assert json.loads(result["topics"]) == ["old"]
