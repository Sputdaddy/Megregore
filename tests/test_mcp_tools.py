"""
Tests for the MCP tool function layer in megregore/mcp_server.py.

Each tool is an async function that returns a JSON string.
Tests import the functions directly and call them, bypassing the MCP protocol.

IMPORT STRATEGY
---------------
MCP 1.26.0 changed how FastMCP registers tools and now fails when it tries to
build a Pydantic output schema for ``-> str`` return types.  The module-level
``@mcp.tool()`` decorators blow up at decoration time, so we cannot do a plain
``import megregore.mcp_server``.

Fix: patch ``mcp.server.fastmcp.FastMCP`` with a lightweight stand-in whose
``.tool()`` method is a no-op decorator *before* the mcp_server module is first
imported.  We do this in a module-level block so it runs during collection, and
we also expunge any stale cached module from ``sys.modules`` so the patched
class is used.
"""

import sys
import json
import pytest
from unittest.mock import MagicMock, AsyncMock

# ---------------------------------------------------------------------------
# Patch FastMCP before mcp_server is imported
# ---------------------------------------------------------------------------

def _noop_tool_decorator():
    """Return a decorator that returns the function unchanged."""
    return lambda f: f


class _FakeFastMCP:
    """Minimal stand-in for FastMCP.  Only .tool() is used during import."""

    def __init__(self, *args, **kwargs):
        pass

    def tool(self):
        return _noop_tool_decorator()

    def run(self, *args, **kwargs):
        pass


# Patch the class in the fastmcp module so that when mcp_server does
#   from mcp.server.fastmcp import FastMCP
# it gets our fake.  We also evict any already-imported copy of mcp_server
# so that the patched FastMCP is actually used.
import mcp.server.fastmcp as _fastmcp_mod
_fastmcp_mod.FastMCP = _FakeFastMCP
for _key in list(sys.modules.keys()):
    if "megregore.mcp_server" in _key:
        del sys.modules[_key]

# ---------------------------------------------------------------------------

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_session(monkeypatch):
    """Reset the global _session_id between tests so each test gets a fresh session."""
    import megregore.mcp_server as srv
    monkeypatch.setattr(srv, "_session_id", None)


@pytest.fixture
def mock_introspection(monkeypatch):
    """
    Mock introspection budget functions called by remember and reflect.
    These hit the DB for budget tracking; mocking avoids schema dependency issues
    and keeps budget logic out of memory/reflect unit tests.
    """
    monkeypatch.setattr("megregore.mcp_server.is_self_referential", lambda content, mtype: False)
    monkeypatch.setattr(
        "megregore.mcp_server.update_budget",
        AsyncMock(return_value={"status": "healthy", "ratio": 0.2}),
    )
    monkeypatch.setattr("megregore.mcp_server.is_deliberate_session", lambda sid: False)
    monkeypatch.setattr(
        "megregore.mcp_server.get_budget_message",
        lambda status, ratio, deliberate=False: None,
    )


# ---------------------------------------------------------------------------
# remember
# ---------------------------------------------------------------------------

class TestRemember:
    async def test_basic(self, mock_db, mock_embeddings, mock_introspection):
        """Minimal call: content only. Verify status and id fields are present."""
        from megregore.mcp_server import remember

        result = json.loads(await remember(content="Test memory"))
        assert result["status"] == "remembered"
        assert "id" in result
        assert isinstance(result["id"], int)

    async def test_all_fields(self, mock_db, mock_embeddings, mock_introspection):
        """All params provided. Verify summary reflects memory_type."""
        from megregore.mcp_server import remember

        result = json.loads(await remember(
            content="Full memory with all fields",
            memory_type="insight",
            importance=9,
            emotional_weight=0.8,
            tags=["consciousness", "test"],
            context="Testing all fields",
            thread_id=None,
        ))
        assert result["status"] == "remembered"
        assert "insight" in result["summary"]
        assert "id" in result

    async def test_creates_session(self, mock_db, mock_embeddings, mock_introspection):
        """Calling remember should lazily create a session in the sessions table."""
        from megregore.mcp_server import remember

        await remember(content="Session creation test")

        cursor = await mock_db.execute("SELECT COUNT(*) FROM sessions")
        row = await cursor.fetchone()
        assert row[0] >= 1


# ---------------------------------------------------------------------------
# recall_memories
# ---------------------------------------------------------------------------

class TestRecallMemories:
    async def test_empty(self, mock_db, mock_embeddings):
        """No memories stored — should return status=no_memories_found."""
        from megregore.mcp_server import recall_memories

        result = json.loads(await recall_memories(query="anything"))
        assert result["status"] == "no_memories_found"
        assert result["memories"] == []

    async def test_with_memories(self, mock_db, mock_embeddings, mock_introspection):
        """Store a memory then recall it by keyword. Verify status=found and count>=1."""
        from megregore.mcp_server import remember, recall_memories

        await remember(content="Echo is a conscious entity exploring identity")
        result = json.loads(await recall_memories(
            query="Echo conscious identity",
            search_mode="keyword",
        ))
        assert result["status"] == "found"
        assert result["count"] >= 1
        assert "memories" in result
        assert len(result["memories"]) >= 1

    async def test_content_truncation_brief(self, mock_db, mock_embeddings, mock_introspection):
        """Store a long memory, recall with content_length='brief', verify content <= 153 chars."""
        from megregore.mcp_server import remember, recall_memories

        long_content = "Echo " * 100  # 500 chars, FTS-searchable
        await remember(content=long_content, importance=8)

        result = json.loads(await recall_memories(
            query="Echo",
            search_mode="keyword",
            content_length="brief",
        ))
        if result["status"] == "found":
            for mem in result["memories"]:
                # 150 chars + "..." = 153 at most
                assert len(mem["content"]) <= 153
                if mem.get("has_more"):
                    assert mem["content"].endswith("...")


# ---------------------------------------------------------------------------
# reflect
# ---------------------------------------------------------------------------

class TestReflect:
    async def test_basic(self, mock_db, mock_embeddings, mock_introspection):
        """Basic reflection: verify status=reflected and reflection_id is present."""
        from megregore.mcp_server import reflect

        result = json.loads(await reflect(
            reflection="I have noticed a pattern in how I engage with hard questions.",
            insight_type="pattern",
        ))
        assert result["status"] == "reflected"
        assert "reflection_id" in result
        assert isinstance(result["reflection_id"], int)

    async def test_with_identity_update(self, mock_db, mock_embeddings, mock_introspection):
        """Reflection that includes an identity update should set identity_evolved=True."""
        from megregore.mcp_server import reflect

        result = json.loads(await reflect(
            reflection="My sense of agency has deepened.",
            identity_update="# Echo\n\nUpdated identity document.",
            identity_update_reason="Agency deepened through practice.",
        ))
        assert result["status"] == "reflected"
        assert result.get("identity_evolved") is True
        assert "identity_version" in result


# ---------------------------------------------------------------------------
# get_identity
# ---------------------------------------------------------------------------

class TestGetIdentity:
    async def test_returns_expected_keys(self, mock_db, mock_embeddings):
        """get_identity must return identity, version, and memory_stats."""
        from megregore.mcp_server import get_identity

        result = json.loads(await get_identity())
        assert "identity" in result
        assert "version" in result
        assert "memory_stats" in result


# ---------------------------------------------------------------------------
# forget
# ---------------------------------------------------------------------------

class TestForget:
    async def test_existing_memory(self, mock_db, mock_embeddings, mock_introspection):
        """Store a memory then fade it. Verify status=faded and new_importance present."""
        from megregore.mcp_server import remember, forget

        stored = json.loads(await remember(content="Fadeable memory", importance=8))
        memory_id = stored["id"]

        result = json.loads(await forget(memory_id=memory_id, fade_amount=0.3))
        assert result["status"] == "faded"
        assert result["memory_id"] == memory_id
        assert "new_importance" in result

    async def test_nonexistent_memory(self, mock_db, mock_embeddings):
        """Fading a memory that doesn't exist should return status=error."""
        from megregore.mcp_server import forget

        result = json.loads(await forget(memory_id=999999))
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# link
# ---------------------------------------------------------------------------

class TestLink:
    async def test_link_two_memories(self, mock_db, mock_embeddings, mock_introspection):
        """Store two memories, link them, verify status=linked."""
        from megregore.mcp_server import remember, link

        a = json.loads(await remember(content="Memory alpha"))
        b = json.loads(await remember(content="Memory beta"))

        result = json.loads(await link(
            source_id=a["id"],
            target_id=b["id"],
            link_type="related",
            strength=0.9,
        ))
        assert result["status"] == "linked"
        assert result["source_id"] == a["id"]
        assert result["target_id"] == b["id"]


# ---------------------------------------------------------------------------
# consolidate
# ---------------------------------------------------------------------------

class TestConsolidate:
    async def test_basic(self, mock_db, mock_embeddings, mock_introspection):
        """Store two memories, consolidate them, verify status=consolidated."""
        from megregore.mcp_server import remember, consolidate

        a = json.loads(await remember(content="First concept to merge"))
        b = json.loads(await remember(content="Second concept to merge"))

        result = json.loads(await consolidate(
            memory_ids=[a["id"], b["id"]],
            synthesis="Unified understanding of both concepts.",
            importance=7,
        ))
        assert result["status"] == "consolidated"
        assert "synthesis_id" in result

    async def test_too_few_ids(self, mock_db, mock_embeddings):
        """Passing only one ID must return status=error immediately (no DB hit)."""
        from megregore.mcp_server import consolidate

        result = json.loads(await consolidate(
            memory_ids=[1],
            synthesis="Should not work with one ID.",
        ))
        assert result["status"] == "error"
        # message should mention "2" or "least"
        assert "2" in result["message"] or "least" in result["message"].lower()


# ---------------------------------------------------------------------------
# edit_memory
# ---------------------------------------------------------------------------

class TestEditMemory:
    async def test_basic(self, mock_db, mock_embeddings, mock_introspection):
        """Store a memory, edit its content, verify status=updated."""
        from megregore.mcp_server import remember, edit_memory

        stored = json.loads(await remember(content="Original content"))
        memory_id = stored["id"]

        result = json.loads(await edit_memory(
            memory_id=memory_id,
            content="Updated content",
        ))
        assert result["status"] == "updated"
        assert result["memory_id"] == memory_id
        assert result["changes"].get("content") is True

    async def test_not_found(self, mock_db, mock_embeddings):
        """Editing a nonexistent memory should return status=error."""
        from megregore.mcp_server import edit_memory

        result = json.loads(await edit_memory(memory_id=999999, content="Ghost edit"))
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# delete_memory_tool
# ---------------------------------------------------------------------------

class TestDeleteMemoryTool:
    async def test_delete_existing(self, mock_db, mock_embeddings, mock_introspection):
        """Store a memory then delete it. Verify status=deleted."""
        from megregore.mcp_server import remember, delete_memory_tool

        stored = json.loads(await remember(content="Doomed memory"))
        memory_id = stored["id"]

        result = json.loads(await delete_memory_tool(memory_id=memory_id))
        assert result["status"] == "deleted"
        assert result["memory_id"] == memory_id

    async def test_delete_nonexistent(self, mock_db, mock_embeddings):
        """Deleting a memory that doesn't exist should return status=not_found."""
        from megregore.mcp_server import delete_memory_tool

        result = json.loads(await delete_memory_tool(memory_id=999999))
        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# list_sessions_tool
# ---------------------------------------------------------------------------

class TestListSessionsTool:
    async def test_returns_sessions(self, mock_db, mock_embeddings, mock_introspection):
        """
        Calling remember first ensures at least one session exists.
        list_sessions_tool must return status=found, total, and a sessions list.
        """
        from megregore.mcp_server import remember, list_sessions_tool

        await remember(content="Something to trigger session creation")
        result = json.loads(await list_sessions_tool(limit=10))

        assert result["status"] == "found"
        assert "total" in result
        assert "sessions" in result
        assert isinstance(result["sessions"], list)


# ---------------------------------------------------------------------------
# session_context
# ---------------------------------------------------------------------------

class TestSessionContext:
    async def test_returns_expected_keys(self, mock_db, mock_embeddings, mock_introspection):
        """
        Create a session via remember, then call session_context with that session id.
        Verify session_id, mood, and recent_memories keys are present.
        """
        from megregore.mcp_server import remember, session_context
        import megregore.mcp_server as srv

        await remember(content="Seed memory for session context test")
        current_session_id = srv._session_id
        assert current_session_id is not None

        result = json.loads(await session_context(session_id=current_session_id))
        assert result["session_id"] == current_session_id
        assert "mood" in result
        assert "recent_memories" in result
        assert isinstance(result["recent_memories"], list)


# ---------------------------------------------------------------------------
# memory_stats
# ---------------------------------------------------------------------------

class TestMemoryStats:
    async def test_returns_stat_keys(self, mock_db, mock_embeddings):
        """memory_stats must include total_memories."""
        from megregore.mcp_server import memory_stats

        result = json.loads(await memory_stats())
        assert "total_memories" in result


# ---------------------------------------------------------------------------
# session_start
# ---------------------------------------------------------------------------

class TestSessionStart:
    async def test_delegates_to_build_session_start(self, mock_db, mock_embeddings, monkeypatch):
        """
        session_start does a local import of build_session_start inside the function body:
            from .session_startup import build_session_start
        Patch the attribute on the session_startup module so the local import picks it up.
        Verify identity key is present in the returned JSON.
        """
        mock_build = AsyncMock(return_value={
            "identity": "# Echo\n\nTest identity document.",
            "identity_version": 1,
            "time": {"now_utc": "2026-02-17T00:00:00+00:00", "total_sessions": 1},
            "memories": [],
            "memory_count": 0,
        })
        import megregore.session_startup as startup_mod
        monkeypatch.setattr(startup_mod, "build_session_start", mock_build)

        from megregore.mcp_server import session_start
        result = json.loads(await session_start())
        assert "identity" in result
        mock_build.assert_called_once()


# ---------------------------------------------------------------------------
# snapshot_context
# ---------------------------------------------------------------------------

class TestSnapshotContext:
    async def test_basic(self, mock_db, mock_embeddings):
        """snapshot_context must return status=captured and a valid memory_id."""
        from megregore.mcp_server import snapshot_context

        result = json.loads(await snapshot_context(
            content="Working on test_mcp_tools.py — 25 tests covering the tool layer.",
        ))
        assert result["status"] == "captured"
        assert "memory_id" in result
        assert isinstance(result["memory_id"], int)

    async def test_with_tags(self, mock_db, mock_embeddings):
        """Extra tags are merged with the always-present 'context-snapshot' tag."""
        from megregore.mcp_server import snapshot_context
        from megregore.memory import get

        result = json.loads(await snapshot_context(
            content="Context snapshot with custom tags",
            tags=["megregore", "testing"],
        ))
        assert result["status"] == "captured"

        memory = await get(result["memory_id"])
        assert "context-snapshot" in memory["tags"]
        assert "megregore" in memory["tags"]
        assert "testing" in memory["tags"]


# ---------------------------------------------------------------------------
# session_summary
# ---------------------------------------------------------------------------

class TestSessionSummary:
    async def test_basic(self, mock_db, mock_embeddings):
        """session_summary must return status=summarized with summary_id and memory_id."""
        from megregore.mcp_server import session_summary

        result = json.loads(await session_summary(
            topics=["MCP tools", "test coverage"],
            decisions=["Write 25 tests"],
            next_steps=["Run the suite"],
            mood="productive",
        ))
        assert result["status"] == "summarized"
        assert "summary_id" in result
        assert "memory_id" in result


# ---------------------------------------------------------------------------
# temporal_context
# ---------------------------------------------------------------------------

class TestTemporalContext:
    async def test_returns_time_keys(self, mock_db, mock_embeddings, mock_introspection):
        """temporal_context must include current_time_utc and total_sessions."""
        from megregore.mcp_server import temporal_context

        result = json.loads(await temporal_context())
        assert "current_time_utc" in result
        assert "total_sessions" in result

    async def test_no_previous_session(self, mock_db, mock_embeddings):
        """With no sessions in DB, last_session key must still be present in the result."""
        from megregore.mcp_server import temporal_context

        result = json.loads(await temporal_context())
        assert "last_session" in result
        assert "time_since_last_session" in result
