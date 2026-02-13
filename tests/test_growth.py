"""Tests for megregore.growth — integration score, contradiction resolution, growth snapshots."""

import pytest
import json
from datetime import datetime, timezone, timedelta
from megregore import growth


@pytest.mark.asyncio
async def test_integration_score_empty_db(mock_db):
    score = await growth.compute_integration_score()
    assert score == 0.0


@pytest.mark.asyncio
async def test_integration_score_with_data(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc).isoformat()
    # Insert memories
    await db.execute(
        "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Memory 1", "experience", 5, 0.3, '["tag1"]', "test", 0, now, now),
    )
    await db.execute(
        "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Memory 2", "experience", 5, -0.5, '["tag2"]', "test", 0, now, now),
    )
    # Insert a link between them
    await db.execute(
        "INSERT INTO memory_links (source_memory_id, target_memory_id, link_type, strength, created_at) VALUES (?, ?, ?, ?, ?)",
        (1, 2, "related", 0.8, now),
    )
    await db.commit()

    score = await growth.compute_integration_score()
    assert 0.0 < score <= 1.0


@pytest.mark.asyncio
async def test_contradiction_resolution(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc).isoformat()
    # Insert two memories
    await db.execute(
        "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("I love cats", "experience", 5, 0.5, '["pets"]', "test", 0, now, now),
    )
    await db.execute(
        "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("I hate cats", "experience", 5, -0.3, '["pets"]', "test", 0, now, now),
    )
    # Insert a contradicts link (unresolved)
    await db.execute(
        "INSERT INTO memory_links (source_memory_id, target_memory_id, link_type, strength, created_at) VALUES (?, ?, ?, ?, ?)",
        (1, 2, "contradicts", 0.9, now),
    )
    # Insert a consolidation reflection referencing both memories
    await db.execute(
        "INSERT INTO reflections (content, insight_type, memory_ids, session_id, created_at) VALUES (?, ?, ?, ?, ?)",
        ("I like some cats but not others", "consolidation", "[1, 2]", "test", now),
    )
    await db.commit()

    result = await growth.check_contradiction_resolutions()
    assert result["checked"] == 1
    assert result["newly_resolved"] == 1


@pytest.mark.asyncio
async def test_growth_snapshot_stores(mock_db):
    snapshot = await growth.compute_growth_snapshot(session_id="test")
    assert "integration_score" in snapshot
    assert "total_contradictions" in snapshot

    db = mock_db
    cursor = await db.execute("SELECT COUNT(*) FROM growth_snapshots")
    row = await cursor.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_trajectory_ordering(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(hours=1)
    # Insert two snapshots manually
    await db.execute(
        "INSERT INTO growth_snapshots (integration_score, total_contradictions, resolved_contradictions, resolution_rate, avg_links_per_memory, thread_coverage_pct, consolidation_ratio, unique_topic_count, cross_thread_link_count, emotional_range, integration_delta, session_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (0.5, 2, 1, 0.5, 0.0, 0.0, 0.0, 0, 0, 0.0, 0.0, "test", earlier.isoformat()),
    )
    await db.execute(
        "INSERT INTO growth_snapshots (integration_score, total_contradictions, resolved_contradictions, resolution_rate, avg_links_per_memory, thread_coverage_pct, consolidation_ratio, unique_topic_count, cross_thread_link_count, emotional_range, integration_delta, session_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (0.7, 3, 2, 0.67, 0.0, 0.0, 0.0, 0, 0, 0.0, 0.0, "test", now.isoformat()),
    )
    await db.commit()

    trajectory = await growth.get_growth_trajectory(limit=20)
    assert len(trajectory) == 2
    # Most recent first
    assert trajectory[0]["integration_score"] == 0.7
    assert trajectory[1]["integration_score"] == 0.5


@pytest.mark.asyncio
async def test_should_generate_snapshot_no_data(mock_db):
    assert await growth.should_generate_snapshot() is True
