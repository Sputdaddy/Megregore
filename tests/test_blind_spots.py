"""Tests for megregore.blind_spots — neglected threads, topic deserts, emotional avoidance."""

import pytest
from datetime import datetime, timezone, timedelta
from megregore import blind_spots


@pytest.mark.asyncio
async def test_no_neglected_threads_empty_db(mock_db):
    threads = await blind_spots.detect_neglected_threads()
    assert threads == []


@pytest.mark.asyncio
async def test_neglected_thread_detected(mock_db):
    db = mock_db
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    await db.execute(
        "INSERT INTO threads (title, memory_count, last_active, created_at) VALUES (?, ?, ?, ?)",
        ("Old thread", 5, thirty_days_ago, thirty_days_ago),
    )
    await db.commit()

    threads = await blind_spots.detect_neglected_threads(min_memory_count=3, silence_days=14)
    assert len(threads) == 1
    assert threads[0]["title"] == "Old thread"
    assert threads[0]["days_silent"] >= 29  # at least 29 days


@pytest.mark.asyncio
async def test_topic_desert_detected(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=60)).isoformat()
    recent = (now - timedelta(days=5)).isoformat()

    # Insert old memories with tag "coding" (within 90-day baseline)
    for i in range(5):
        await db.execute(
            "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"Old coding {i}", "experience", 5, 0.0, '["coding"]', "test", 0, old, old),
        )
    # Insert 1 recent memory (within 30-day lookback) — 80% drop
    await db.execute(
        "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Recent coding", "experience", 5, 0.0, '["coding"]', "test", 0, recent, recent),
    )
    await db.commit()

    deserts = await blind_spots.find_topic_deserts(lookback_days=30, baseline_days=90)
    # "coding" should show up as a desert since it dropped from 6 (baseline) to 1 (recent)
    coding_deserts = [d for d in deserts if d["tag"] == "coding"]
    assert len(coding_deserts) == 1
    assert coding_deserts[0]["drop_ratio"] > 0.7


@pytest.mark.asyncio
async def test_emotional_avoidance_no_data(mock_db):
    avoidance = await blind_spots.detect_emotional_avoidance()
    assert avoidance == []


@pytest.mark.asyncio
async def test_blind_spot_scan_stores_report(mock_db):
    report = await blind_spots.run_blind_spot_scan(session_id="test")
    assert "coverage_score" in report
    assert 0.0 <= report["coverage_score"] <= 1.0

    db = mock_db
    cursor = await db.execute("SELECT COUNT(*) FROM blind_spot_reports")
    row = await cursor.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_should_run_scan_no_reports(mock_db):
    assert await blind_spots.should_run_scan() is True


@pytest.mark.asyncio
async def test_blind_spot_history_empty(mock_db):
    history = await blind_spots.get_blind_spot_history(limit=10)
    assert history == []
