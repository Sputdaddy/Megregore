"""Tests for megregore.introspection_budget — self-referential detection and budget tracking."""

import pytest
from datetime import datetime, timezone
from megregore import introspection_budget


def test_is_self_referential_reflection_type():
    assert introspection_budget.is_self_referential("any content", "reflection") is True


def test_is_self_referential_insight_type():
    assert introspection_budget.is_self_referential("any content", "insight") is True


def test_is_self_referential_pattern_match():
    assert introspection_budget.is_self_referential("I think about my memories a lot", "experience") is True


def test_is_self_referential_normal_content():
    assert introspection_budget.is_self_referential("Hunter likes coffee", "experience") is False


def test_budget_message_healthy():
    assert introspection_budget.get_budget_message("healthy", 0.2) == ""


def test_budget_message_warning():
    msg = introspection_budget.get_budget_message("warning", 0.5)
    assert msg != ""
    assert "50%" in msg


def test_budget_message_throttled():
    msg = introspection_budget.get_budget_message("throttled", 0.8)
    assert msg != ""
    assert "80%" in msg


@pytest.mark.asyncio
async def test_update_budget_empty_session(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc).isoformat()
    # Session FK requires a matching sessions row
    await db.execute(
        "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
        ("empty-session", now, now),
    )
    await db.commit()

    budget = await introspection_budget.update_budget("empty-session")
    assert budget["ratio"] == 0.0
    assert budget["status"] == "healthy"
    assert budget["total"] == 0
    assert budget["self_referential"] == 0


@pytest.mark.asyncio
async def test_update_budget_high_ratio(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc).isoformat()
    # Session FK requires a matching sessions row
    await db.execute(
        "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
        ("high-ratio", now, now),
    )
    # Insert 10 memories, 7 self-referential
    for i in range(10):
        is_self = 1 if i < 7 else 0
        await db.execute(
            "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"Memory {i}", "experience", 5, 0.0, "[]", "high-ratio", is_self, now, now),
        )
    await db.commit()

    budget = await introspection_budget.update_budget("high-ratio")
    assert budget["ratio"] == 0.7
    assert budget["status"] == "throttled"


@pytest.mark.asyncio
async def test_get_budget_default(mock_db):
    budget = await introspection_budget.get_budget("nonexistent")
    assert budget["status"] == "healthy"
    assert budget["ratio"] == 0.0


@pytest.mark.asyncio
async def test_budget_history_empty(mock_db):
    history = await introspection_budget.get_budget_history(limit=10)
    assert history == []
