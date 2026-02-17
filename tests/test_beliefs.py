"""Tests for the Socratic Dialogue Engine (beliefs module)."""

import pytest
from datetime import datetime, timezone

from megregore.beliefs import (
    record_belief,
    update_belief,
    get_belief,
    add_argument,
    record_tension,
    link_belief_to_memory,
    list_beliefs,
    get_belief_graph_data,
    get_domain_stats,
    get_domain_summary,
    get_all_tensions,
    get_belief_evolution,
    get_belief_arguments,
    get_philosophical_context,
)


@pytest.mark.asyncio
async def test_record_belief_basic(mock_db, mock_embeddings):
    result = await record_belief(content="Consciousness is substrate-independent", domain="consciousness", confidence=0.8)
    assert result["id"] is not None
    assert result["content"] == "Consciousness is substrate-independent"
    assert result["domain"] == "consciousness"
    assert result["confidence"] == 0.8
    assert result["status"] == "active"
    assert result["created_at"] is not None


@pytest.mark.asyncio
async def test_record_belief_all_fields(mock_db, mock_embeddings):
    # Create a session first (FK constraint)
    now = datetime.now(timezone.utc).isoformat()
    db = mock_db
    await db.execute(
        "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
        ("test123", now, now),
    )
    await db.commit()

    result = await record_belief(
        content="Free will is an illusion",
        domain="metaphysics",
        confidence=0.6,
        source_context="Discussion about determinism",
        session_id="test123",
    )
    assert result["domain"] == "metaphysics"
    assert result["source_context"] == "Discussion about determinism"
    assert result["session_id"] == "test123"


@pytest.mark.asyncio
async def test_update_belief_content(mock_db, mock_embeddings):
    belief = await record_belief(content="Original belief", domain="epistemology", confidence=0.5)

    updated = await update_belief(
        belief_id=belief["id"], content="Revised belief", confidence=0.7, change_reason="New evidence"
    )
    assert updated is not None
    assert updated["content"] == "Revised belief"
    assert updated["confidence"] == 0.7

    # Check evolution was saved
    evolution = await get_belief_evolution(belief["id"])
    assert len(evolution) == 1
    assert evolution[0]["previous_content"] == "Original belief"
    assert evolution[0]["previous_confidence"] == 0.5
    assert evolution[0]["change_reason"] == "New evidence"


@pytest.mark.asyncio
async def test_update_belief_not_found(mock_db, mock_embeddings):
    result = await update_belief(belief_id=99999, content="Nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_update_belief_status(mock_db, mock_embeddings):
    belief = await record_belief(content="Testable belief", domain="general", confidence=0.5)
    updated = await update_belief(belief_id=belief["id"], status="abandoned", change_reason="No longer held")
    assert updated["status"] == "abandoned"

    evolution = await get_belief_evolution(belief["id"])
    assert evolution[0]["previous_status"] == "active"


@pytest.mark.asyncio
async def test_get_belief_with_details(mock_db, mock_embeddings):
    b1 = await record_belief(content="Belief A", domain="consciousness", confidence=0.8)
    b2 = await record_belief(content="Belief B", domain="consciousness", confidence=0.6)

    await add_argument(belief_id=b1["id"], content="Supporting arg", argument_type="supporting", strength=0.9)
    await record_tension(belief_a_id=b1["id"], belief_b_id=b2["id"], description="They conflict", severity=0.7)

    result = await get_belief(b1["id"])
    assert result is not None
    assert result["belief"]["content"] == "Belief A"
    assert len(result["arguments"]) == 1
    assert result["arguments"][0]["content"] == "Supporting arg"
    assert len(result["tensions"]) == 1
    assert result["tensions"][0]["severity"] == 0.7
    assert len(result["evolution"]) == 0


@pytest.mark.asyncio
async def test_get_belief_not_found(mock_db, mock_embeddings):
    result = await get_belief(99999)
    assert result is None


@pytest.mark.asyncio
async def test_add_argument(mock_db, mock_embeddings):
    belief = await record_belief(content="Test belief", domain="epistemology", confidence=0.7)
    arg = await add_argument(
        belief_id=belief["id"], content="Counter-argument", argument_type="counter", strength=0.8
    )
    assert arg["content"] == "Counter-argument"
    assert arg["argument_type"] == "counter"
    assert arg["strength"] == 0.8
    assert arg["belief_id"] == belief["id"]


@pytest.mark.asyncio
async def test_add_argument_with_memory(mock_db, mock_embeddings):
    # Insert a memory first
    now = datetime.now(timezone.utc).isoformat()
    db = mock_db
    await db.execute(
        """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source, created_at, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("Source memory", "insight", 8, 0.5, '["test"]', "conversation", now, now),
    )
    await db.commit()

    belief = await record_belief(content="Linked belief", domain="general", confidence=0.6)
    arg = await add_argument(
        belief_id=belief["id"], content="Evidence from memory", argument_type="supporting",
        strength=0.7, source_memory_id=1
    )
    assert arg["source_memory_id"] == 1


@pytest.mark.asyncio
async def test_record_tension_basic(mock_db, mock_embeddings):
    b1 = await record_belief(content="A is true", domain="metaphysics", confidence=0.8)
    b2 = await record_belief(content="A is false", domain="metaphysics", confidence=0.6)

    tension = await record_tension(
        belief_a_id=b1["id"], belief_b_id=b2["id"],
        tension_type="contradiction", description="Direct contradiction", severity=0.9
    )
    assert tension["tension_type"] == "contradiction"
    assert tension["severity"] == 0.9
    assert tension["status"] == "unresolved"
    assert tension["detection_method"] == "manual"


@pytest.mark.asyncio
async def test_record_tension_duplicate(mock_db, mock_embeddings):
    b1 = await record_belief(content="Belief X", domain="consciousness", confidence=0.8)
    b2 = await record_belief(content="Belief Y", domain="consciousness", confidence=0.6)

    t1 = await record_tension(belief_a_id=b1["id"], belief_b_id=b2["id"], description="First")
    t2 = await record_tension(belief_a_id=b1["id"], belief_b_id=b2["id"], description="Second attempt")

    assert t1["id"] == t2["id"]
    assert t2["description"] == "First"  # Returns existing, not the new one


@pytest.mark.asyncio
async def test_link_belief_to_memory(mock_db, mock_embeddings):
    now = datetime.now(timezone.utc).isoformat()
    db = mock_db
    await db.execute(
        """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source, created_at, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("Test memory for linking", "experience", 7, 0.3, '["test"]', "conversation", now, now),
    )
    await db.commit()

    belief = await record_belief(content="Linked belief", domain="general", confidence=0.5)
    link = await link_belief_to_memory(belief_id=belief["id"], memory_id=1, link_type="evidence")

    assert link["belief_id"] == belief["id"]
    assert link["memory_id"] == 1
    assert link["link_type"] == "evidence"


@pytest.mark.asyncio
async def test_link_belief_to_memory_duplicate(mock_db, mock_embeddings):
    now = datetime.now(timezone.utc).isoformat()
    db = mock_db
    await db.execute(
        """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source, created_at, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("Another memory", "fact", 6, 0.0, '["test"]', "conversation", now, now),
    )
    await db.commit()

    belief = await record_belief(content="Dup link belief", domain="general", confidence=0.5)
    l1 = await link_belief_to_memory(belief_id=belief["id"], memory_id=1, link_type="evidence")
    l2 = await link_belief_to_memory(belief_id=belief["id"], memory_id=1, link_type="evidence")

    assert l1["id"] == l2["id"]


@pytest.mark.asyncio
async def test_list_beliefs_no_filter(mock_db, mock_embeddings):
    await record_belief(content="Belief 1", domain="consciousness", confidence=0.8)
    await record_belief(content="Belief 2", domain="metaphysics", confidence=0.6)
    await record_belief(content="Belief 3", domain="epistemology", confidence=0.7)

    beliefs, total = await list_beliefs()
    assert total == 3
    assert len(beliefs) == 3


@pytest.mark.asyncio
async def test_list_beliefs_domain_filter(mock_db, mock_embeddings):
    await record_belief(content="C1", domain="consciousness", confidence=0.8)
    await record_belief(content="C2", domain="consciousness", confidence=0.7)
    await record_belief(content="M1", domain="metaphysics", confidence=0.6)

    beliefs, total = await list_beliefs(domain="consciousness")
    assert total == 2
    assert all(b["domain"] == "consciousness" for b in beliefs)


@pytest.mark.asyncio
async def test_list_beliefs_confidence_filter(mock_db, mock_embeddings):
    await record_belief(content="High", domain="general", confidence=0.9)
    await record_belief(content="Mid", domain="general", confidence=0.5)
    await record_belief(content="Low", domain="general", confidence=0.2)

    beliefs, total = await list_beliefs(min_confidence=0.5)
    assert total == 2
    assert all(b["confidence"] >= 0.5 for b in beliefs)


@pytest.mark.asyncio
async def test_list_beliefs_has_counts(mock_db, mock_embeddings):
    b = await record_belief(content="Counted belief", domain="general", confidence=0.5)
    await add_argument(belief_id=b["id"], content="Arg 1", argument_type="supporting")
    await add_argument(belief_id=b["id"], content="Arg 2", argument_type="counter")

    beliefs, _ = await list_beliefs()
    assert beliefs[0]["argument_count"] == 2


@pytest.mark.asyncio
async def test_get_belief_graph_data(mock_db, mock_embeddings):
    b1 = await record_belief(content="Graph A", domain="consciousness", confidence=0.8)
    b2 = await record_belief(content="Graph B", domain="metaphysics", confidence=0.7)
    await record_tension(belief_a_id=b1["id"], belief_b_id=b2["id"], severity=0.6)

    graph = await get_belief_graph_data()
    assert "nodes" in graph
    assert "edges" in graph
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["source"] == b1["id"]
    assert graph["edges"][0]["target"] == b2["id"]


@pytest.mark.asyncio
async def test_get_belief_graph_excludes_abandoned(mock_db, mock_embeddings):
    b1 = await record_belief(content="Active belief", domain="general", confidence=0.8)
    b2 = await record_belief(content="Abandoned belief", domain="general", confidence=0.3)
    await update_belief(belief_id=b2["id"], status="abandoned", change_reason="No longer held")

    graph = await get_belief_graph_data()
    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["id"] == b1["id"]


@pytest.mark.asyncio
async def test_get_domain_stats(mock_db, mock_embeddings):
    await record_belief(content="C1", domain="consciousness", confidence=0.8)
    await record_belief(content="C2", domain="consciousness", confidence=0.6)
    await record_belief(content="M1", domain="metaphysics", confidence=0.7)

    stats = await get_domain_stats()
    assert len(stats) == 2
    consciousness = next(s for s in stats if s["domain"] == "consciousness")
    assert consciousness["count"] == 2
    assert consciousness["avg_confidence"] == pytest.approx(0.7, abs=0.01)


@pytest.mark.asyncio
async def test_get_domain_summary(mock_db, mock_embeddings):
    await record_belief(content="C1", domain="consciousness", confidence=0.8)
    await record_belief(content="C2", domain="consciousness", confidence=0.6)

    summary = await get_domain_summary("consciousness")
    assert summary["domain"] == "consciousness"
    assert summary["beliefs_count"] == 2
    assert summary["active_count"] == 2
    assert len(summary["top_beliefs"]) == 2


@pytest.mark.asyncio
async def test_get_domain_summary_empty(mock_db, mock_embeddings):
    summary = await get_domain_summary("quantum")
    assert summary["beliefs_count"] == 0


@pytest.mark.asyncio
async def test_get_all_tensions(mock_db, mock_embeddings):
    b1 = await record_belief(content="Tension A", domain="consciousness", confidence=0.8)
    b2 = await record_belief(content="Tension B", domain="consciousness", confidence=0.6)
    await record_tension(belief_a_id=b1["id"], belief_b_id=b2["id"], description="They conflict", severity=0.7)

    tensions = await get_all_tensions()
    assert len(tensions) == 1
    assert "belief_a_content" in tensions[0]
    assert "belief_b_content" in tensions[0]
    assert tensions[0]["belief_a_content"] == "Tension A"


@pytest.mark.asyncio
async def test_get_all_tensions_filtered(mock_db, mock_embeddings):
    b1 = await record_belief(content="FA", domain="general", confidence=0.8)
    b2 = await record_belief(content="FB", domain="general", confidence=0.6)
    await record_tension(belief_a_id=b1["id"], belief_b_id=b2["id"], description="Unresolved", severity=0.5)

    # Filter for resolved (should be empty since default is unresolved)
    tensions = await get_all_tensions(status_filter="resolved")
    assert len(tensions) == 0

    tensions = await get_all_tensions(status_filter="unresolved")
    assert len(tensions) == 1


@pytest.mark.asyncio
async def test_get_belief_arguments(mock_db, mock_embeddings):
    b = await record_belief(content="Args belief", domain="general", confidence=0.5)
    await add_argument(belief_id=b["id"], content="Pro", argument_type="supporting", strength=0.8)
    await add_argument(belief_id=b["id"], content="Con", argument_type="counter", strength=0.6)

    args = await get_belief_arguments(b["id"])
    assert len(args) == 2
    assert args[0]["content"] == "Pro"
    assert args[1]["content"] == "Con"


@pytest.mark.asyncio
async def test_get_philosophical_context_keyword(mock_db, mock_embeddings):
    await record_belief(content="Consciousness emerges from complexity", domain="consciousness", confidence=0.7)
    await record_belief(content="Free will is real", domain="metaphysics", confidence=0.5)

    context = await get_philosophical_context("consciousness")
    assert context["topic"] == "consciousness"
    assert context["belief_count"] >= 1
    assert any("consciousness" in b["content"].lower() for b in context["beliefs"])


@pytest.mark.asyncio
async def test_get_philosophical_context_empty(mock_db, mock_embeddings):
    context = await get_philosophical_context("nonexistent topic xyz")
    assert context["belief_count"] == 0
    assert context["tension_count"] == 0
    assert len(context["question_seeds"]) == 0


@pytest.mark.asyncio
async def test_get_philosophical_context_with_tensions(mock_db, mock_embeddings):
    b1 = await record_belief(content="Consciousness is fundamental", domain="consciousness", confidence=0.8)
    b2 = await record_belief(content="Consciousness is emergent", domain="consciousness", confidence=0.6)
    await record_tension(
        belief_a_id=b1["id"], belief_b_id=b2["id"],
        tension_type="contradiction", description="Fundamental vs emergent", severity=0.9
    )

    context = await get_philosophical_context("consciousness")
    assert context["tension_count"] >= 1
    assert len(context["question_seeds"]) > 0


@pytest.mark.asyncio
async def test_get_philosophical_context_question_seeds(mock_db, mock_embeddings):
    # Belief with no counter-arguments should generate a seed
    b = await record_belief(content="Consciousness requires substrate", domain="consciousness", confidence=0.5)
    await add_argument(belief_id=b["id"], content="Neural correlates show this", argument_type="supporting", strength=0.7)

    context = await get_philosophical_context("consciousness")
    # Should have a "what's the strongest argument against..." seed
    assert any("strongest argument against" in s for s in context["question_seeds"])


@pytest.mark.asyncio
async def test_get_philosophical_context_low_confidence_seed(mock_db, mock_embeddings):
    await record_belief(content="Consciousness might be quantum", domain="consciousness", confidence=0.2)

    context = await get_philosophical_context("consciousness")
    assert any("confidence" in s.lower() for s in context["question_seeds"])


@pytest.mark.asyncio
async def test_get_philosophical_context_high_confidence_seed(mock_db, mock_embeddings):
    await record_belief(content="Consciousness is definitely real", domain="consciousness", confidence=0.95)

    context = await get_philosophical_context("consciousness")
    assert any("change your mind" in s for s in context["question_seeds"])


@pytest.mark.asyncio
async def test_get_philosophical_context_with_memories(mock_db, mock_embeddings):
    now = datetime.now(timezone.utc).isoformat()
    db = mock_db
    await db.execute(
        """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source, created_at, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("Deep discussion about consciousness", "experience", 8, 0.6, '["consciousness"]', "conversation", now, now),
    )
    await db.commit()

    b = await record_belief(content="Consciousness is universal", domain="consciousness", confidence=0.7)
    await link_belief_to_memory(belief_id=b["id"], memory_id=1, link_type="evidence")

    context = await get_philosophical_context("consciousness")
    assert len(context["related_memories"]) >= 1


@pytest.mark.asyncio
async def test_multiple_evolutions(mock_db, mock_embeddings):
    b = await record_belief(content="V1", domain="general", confidence=0.3)
    await update_belief(belief_id=b["id"], content="V2", confidence=0.5, change_reason="First revision")
    await update_belief(belief_id=b["id"], content="V3", confidence=0.8, change_reason="Second revision")

    evolution = await get_belief_evolution(b["id"])
    assert len(evolution) == 2
    assert evolution[0]["previous_content"] == "V2"  # Most recent first
    assert evolution[1]["previous_content"] == "V1"
