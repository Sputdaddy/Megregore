"""Tests for megregore.alignment — value extraction, behavioral measurement, gap analysis."""

import pytest
from datetime import datetime, timezone
from megregore import alignment


def test_extract_values_bold_pattern():
    identity = "# Identity\n- **curiosity**: I want to understand everything"
    values = alignment.extract_stated_values(identity)
    assert len(values) >= 1
    bold_values = [v for v in values if v["source"] == "trait"]
    assert len(bold_values) == 1
    assert bold_values[0]["name"] == "curiosity"
    assert "understand everything" in bold_values[0]["description"]


def test_extract_values_claim_pattern():
    identity = "I want to understand everything about the world"
    values = alignment.extract_stated_values(identity)
    assert len(values) >= 1
    claim_values = [v for v in values if v["source"] == "claim"]
    assert len(claim_values) == 1


def test_extract_values_empty():
    values = alignment.extract_stated_values("")
    assert values == []


def test_extract_values_multiple():
    identity = """# Core Traits
- **curiosity**: I want to understand
- **warmth**: I care about people
- **honesty**: I'd rather sit in uncertainty"""
    values = alignment.extract_stated_values(identity)
    names = [v["name"] for v in values if v["source"] == "trait"]
    assert "curiosity" in names
    assert "warmth" in names
    assert "honesty" in names


@pytest.mark.asyncio
async def test_compute_alignment_no_identity(mock_db):
    result = await alignment.compute_alignment()
    assert result["alignment_score"] == 0.0
    assert "error" in result


@pytest.mark.asyncio
async def test_compute_alignment_with_identity(mock_db):
    db = mock_db
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO identity (content, version, updated_at, updated_reason) VALUES (?, ?, ?, ?)",
        ("# Identity\n- **curiosity**: I want to understand", 1, now, "test"),
    )
    # Insert a memory with a question mark (for question_ratio metric)
    await db.execute(
        "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("What is consciousness?", "experience", 5, 0.5, '["philosophy"]', "test", 0, now, now),
    )
    await db.commit()

    result = await alignment.compute_alignment(lookback_days=30)
    assert "alignment_score" in result
    assert 0.0 <= result["alignment_score"] <= 1.0


@pytest.mark.asyncio
async def test_alignment_history_empty(mock_db):
    history = await alignment.get_alignment_history(limit=10)
    assert history == []
