"""Tests for megregore.self_model — predictions, evaluation, surprise scoring."""

import pytest
from datetime import datetime, timezone
from megregore import self_model


@pytest.mark.asyncio
async def test_make_prediction_stores(mock_db):
    result = await self_model.make_prediction(
        prediction="I will store more experience memories than insights",
        prediction_type="behavioral",
        confidence=0.7,
        timeframe_hours=168.0,
        evaluation_criteria={"expected_dominant_type": "experience", "expected_ratio": 0.6},
        session_id="test",
    )
    assert result["status"] == "predicted"
    assert "prediction_id" in result

    db = mock_db
    cursor = await db.execute("SELECT COUNT(*) FROM self_predictions")
    row = await cursor.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_prediction_default_status(mock_db):
    result = await self_model.make_prediction(
        prediction="Test prediction",
        prediction_type="behavioral",
        confidence=0.5,
        timeframe_hours=1.0,
        session_id="test",
    )
    assert result["status"] == "predicted"

    # Verify DB row has 'pending' status
    db = mock_db
    cursor = await db.execute("SELECT status FROM self_predictions WHERE id = ?", (result["prediction_id"],))
    row = await cursor.fetchone()
    assert row[0] == "pending"


@pytest.mark.asyncio
async def test_evaluate_no_pending(mock_db):
    result = await self_model.evaluate_pending_predictions()
    assert result["evaluated"] == 0
    assert result["verified"] == 0
    assert result["falsified"] == 0


@pytest.mark.asyncio
async def test_accuracy_no_data(mock_db):
    accuracy = await self_model.get_prediction_accuracy()
    assert accuracy["total_evaluated"] == 0
    assert accuracy["accuracy"] == 0.0
    assert accuracy["avg_surprise"] == 0.0


@pytest.mark.asyncio
async def test_surprising_outcomes_empty(mock_db):
    outcomes = await self_model.get_surprising_outcomes()
    assert outcomes == []


@pytest.mark.asyncio
async def test_generate_prediction_no_memories(mock_db):
    result = await self_model.generate_behavioral_prediction(session_id="test")
    assert result["status"] == "skipped"
    assert "reason" in result


@pytest.mark.asyncio
async def test_generate_prediction_with_memories(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc).isoformat()
    # Insert 20 memories so the generator has enough data
    for i in range(20):
        await db.execute(
            "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"Memory {i}", "experience", 5, 0.0, "[]", "test", 0, now, now),
        )
    await db.commit()

    result = await self_model.generate_behavioral_prediction(session_id="test")
    assert result["status"] == "predicted"
    assert "prediction_id" in result
