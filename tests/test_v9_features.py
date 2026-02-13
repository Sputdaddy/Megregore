"""Tests for Megregore V9: improved alignment, introspection context, procedural memory."""

import pytest
from datetime import datetime, timedelta, timezone
from megregore import alignment, introspection_budget
from megregore.decay import compute_half_life, decay_activation


# --- Feature 1: Improved Alignment Proxies ---


class TestSemanticSimilarityCount:
    """Tests for _semantic_similarity_count helper."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_chroma_unavailable(self, mock_db, monkeypatch):
        async def mock_unavailable():
            return False

        monkeypatch.setattr("megregore.alignment.embeddings.is_available", mock_unavailable)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        matching, total = await alignment._semantic_similarity_count(
            ["test phrase"], cutoff
        )
        assert matching == 0

    @pytest.mark.asyncio
    async def test_counts_matching_memories(self, mock_db, monkeypatch):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Insert memories
        for i in range(5):
            await db.execute(
                "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, "
                "is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"Memory {i}", "experience", 5, 0.0, "[]", 0, now, now),
            )
        await db.commit()

        # Mock semantic search to return memory IDs 1-3 with high similarity
        async def mock_search(query, limit=20):
            return [(1, 0.8), (2, 0.7), (3, 0.65), (4, 0.3)]  # ID 4 below threshold

        async def mock_available():
            return True

        monkeypatch.setattr("megregore.alignment.embeddings.semantic_search", mock_search)
        monkeypatch.setattr("megregore.alignment.embeddings.is_available", mock_available)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        matching, total = await alignment._semantic_similarity_count(
            ["inquiry phrase"], cutoff, threshold=0.6
        )
        assert matching == 3
        assert total == 5


class TestImprovedCuriosityMetric:
    @pytest.mark.asyncio
    async def test_tag_diversity_signal(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Insert memories with diverse tags
        tags_sets = [
            '["python", "coding"]',
            '["consciousness", "philosophy"]',
            '["megregore", "architecture"]',
            '["hunter", "friendship"]',
        ]
        for tags in tags_sets:
            await db.execute(
                "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, "
                "is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("Test memory", "experience", 5, 0.0, tags, 0, now, now),
            )
        await db.commit()

        score = await alignment._measure_metric("curiosity", 30)
        # With 8 unique tags, tag diversity signal = 8/30 ≈ 0.27
        # No semantic signal (mock returns empty), no cross-thread links
        assert 0.0 < score < 1.0

    @pytest.mark.asyncio
    async def test_cross_thread_linking_signal(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Create two threads
        await db.execute(
            "INSERT INTO threads (id, title, created_at, last_active) VALUES (?, ?, ?, ?)",
            (1, "Thread A", now, now),
        )
        await db.execute(
            "INSERT INTO threads (id, title, created_at, last_active) VALUES (?, ?, ?, ?)",
            (2, "Thread B", now, now),
        )
        # Insert memories in different threads
        await db.execute(
            "INSERT INTO memories (id, content, memory_type, importance, emotional_weight, tags, "
            "thread_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "Memory A", "experience", 5, 0.0, "[]", 1, 0, now, now),
        )
        await db.execute(
            "INSERT INTO memories (id, content, memory_type, importance, emotional_weight, tags, "
            "thread_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (2, "Memory B", "experience", 5, 0.0, "[]", 2, 0, now, now),
        )
        # Create cross-thread link
        await db.execute(
            "INSERT INTO memory_links (source_memory_id, target_memory_id, link_type, strength, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 2, "related", 1.0, now),
        )
        await db.commit()

        score = await alignment._measure_metric("curiosity", 30)
        # Cross-thread link signal = 1/8 = 0.125
        assert score > 0


class TestImprovedPersistenceMetric:
    @pytest.mark.asyncio
    async def test_zero_without_cross_session_access(self, mock_db, mock_embeddings):
        score = await alignment._measure_metric("quiet_persistence", 30)
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_scores_with_multi_session_access(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Create thread, memory, sessions
        await db.execute(
            "INSERT INTO threads (id, title, created_at, last_active) VALUES (?, ?, ?, ?)",
            (1, "Test thread", now, now),
        )
        await db.execute(
            "INSERT INTO memories (id, content, memory_type, importance, emotional_weight, tags, "
            "thread_id, access_count, is_self_referential, created_at, last_accessed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "Test", "experience", 5, 0.0, "[]", 1, 5, 0, now, now),
        )
        await db.execute(
            "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            ("s1", now, now),
        )
        await db.execute(
            "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            ("s2", now, now),
        )
        await db.execute(
            "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            ("s3", now, now),
        )
        # Access from 3 different sessions
        for sid in ["s1", "s2", "s3"]:
            await db.execute(
                "INSERT INTO memory_access_log (memory_id, access_type, session_id, accessed_at) "
                "VALUES (?, ?, ?, ?)",
                (1, "recall", sid, now),
            )
        await db.commit()

        score = await alignment._measure_metric("quiet_persistence", 30)
        assert score > 0


class TestImprovedHonestyMetric:
    @pytest.mark.asyncio
    async def test_self_correction_acknowledgment(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Insert memory with self-correction tag
        await db.execute(
            "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, "
            "is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("I was wrong about this approach", "insight", 7, -0.2,
             '["self-correction"]', 1, now, now),
        )
        await db.commit()

        score = await alignment._measure_metric("honesty", 30)
        assert score > 0

    @pytest.mark.asyncio
    async def test_contradiction_links(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Insert two memories and a contradicts link
        for i in range(2):
            await db.execute(
                "INSERT INTO memories (id, content, memory_type, importance, emotional_weight, tags, "
                "is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (i + 1, f"Memory {i}", "experience", 5, 0.0, "[]", 0, now, now),
            )
        await db.execute(
            "INSERT INTO memory_links (source_memory_id, target_memory_id, link_type, strength, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 2, "contradicts", 1.0, now),
        )
        await db.commit()

        score = await alignment._measure_metric("honesty", 30)
        assert score > 0


class TestImprovedSelfCorrectionMetric:
    @pytest.mark.asyncio
    async def test_grounded_reflections(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Insert grounded reflection (has memory_ids)
        await db.execute(
            "INSERT INTO reflections (content, memory_ids, insight_type, created_at) VALUES (?, ?, ?, ?)",
            ("I learned something", "[1, 2]", "pattern", now),
        )
        # Insert ungrounded reflection (empty memory_ids)
        await db.execute(
            "INSERT INTO reflections (content, memory_ids, insight_type, created_at) VALUES (?, ?, ?, ?)",
            ("Vague thought", "[]", "pattern", now),
        )
        await db.commit()

        score = await alignment._measure_metric("self_correction", 30)
        # Grounded ratio = 1/2 = 0.5, score1 = 0.5 * 0.4 = 0.2
        assert score > 0

    @pytest.mark.asyncio
    async def test_identity_evolution(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Insert identity update with substantive reason
        await db.execute(
            "INSERT INTO identity (content, version, updated_at, updated_reason) VALUES (?, ?, ?, ?)",
            ("Updated identity", 1, now, "This is a meaningful update reflecting genuine growth and change in perspective"),
        )
        await db.commit()

        score = await alignment._measure_metric("self_correction", 30)
        assert score > 0


class TestUnchangedMetrics:
    @pytest.mark.asyncio
    async def test_warmth_metric(self, mock_db):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, "
            "is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("Warm memory", "experience", 5, 0.6, "[]", 0, now, now),
        )
        await db.commit()

        score = await alignment._measure_metric("positive_emotional_avg", 30)
        assert score > 0

    @pytest.mark.asyncio
    async def test_agency_metric(self, mock_db):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "INSERT INTO identity (content, version, updated_at) VALUES (?, ?, ?)",
            ("Identity", 1, now),
        )
        await db.commit()

        score = await alignment._measure_metric("identity_update_frequency", 30)
        assert score > 0


# --- Feature 2: Introspection Budget Context-Awareness ---


class TestDeliberateIntrospection:
    def test_record_tool_call_tracked(self):
        introspection_budget._session_tool_calls.clear()
        introspection_budget.record_tool_call("test-session", "check_alignment")
        assert "check_alignment" in introspection_budget._session_tool_calls["test-session"]

    def test_non_introspection_tool_not_tracked(self):
        introspection_budget._session_tool_calls.clear()
        introspection_budget.record_tool_call("test-session", "remember")
        assert "test-session" not in introspection_budget._session_tool_calls

    def test_not_deliberate_with_one_tool(self):
        introspection_budget._session_tool_calls.clear()
        introspection_budget.record_tool_call("test-session", "check_alignment")
        assert introspection_budget.is_deliberate_session("test-session") is False

    def test_deliberate_with_two_tools(self):
        introspection_budget._session_tool_calls.clear()
        introspection_budget.record_tool_call("test-session", "check_alignment")
        introspection_budget.record_tool_call("test-session", "measure_growth")
        assert introspection_budget.is_deliberate_session("test-session") is True

    def test_deliberate_with_unknown_session(self):
        introspection_budget._session_tool_calls.clear()
        assert introspection_budget.is_deliberate_session("nonexistent") is False


class TestContextAwareMessages:
    def test_normal_healthy_no_message(self):
        msg = introspection_budget.get_budget_message("healthy", 0.2, deliberate=False)
        assert msg == ""

    def test_normal_warning_has_ratio(self):
        msg = introspection_budget.get_budget_message("warning", 0.5, deliberate=False)
        assert "50%" in msg

    def test_normal_throttled_has_message(self):
        msg = introspection_budget.get_budget_message("throttled", 0.8, deliberate=False)
        assert msg != ""

    def test_deliberate_healthy_no_message(self):
        msg = introspection_budget.get_budget_message("healthy", 0.5, deliberate=True)
        assert msg == ""

    def test_deliberate_warning_different_message(self):
        msg = introspection_budget.get_budget_message("warning", 0.8, deliberate=True)
        assert "introspection session" in msg.lower()
        assert "50%" not in msg  # Should NOT show ratio in deliberate mode

    def test_deliberate_throttled_different_message(self):
        msg = introspection_budget.get_budget_message("throttled", 0.95, deliberate=True)
        assert "introspection session" in msg.lower()


class TestRaisedThresholds:
    @pytest.mark.asyncio
    async def test_normal_session_throttled_at_60pct(self, mock_db):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            ("normal-session", now, now),
        )
        # 7 self-referential out of 10 = 70% -> throttled in normal mode
        for i in range(10):
            is_self = 1 if i < 7 else 0
            await db.execute(
                "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, "
                "session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"Memory {i}", "experience", 5, 0.0, "[]", "normal-session", is_self, now, now),
            )
        await db.commit()

        introspection_budget._session_tool_calls.clear()
        budget = await introspection_budget.update_budget("normal-session")
        assert budget["status"] == "throttled"
        assert budget["mode"] == "normal"

    @pytest.mark.asyncio
    async def test_deliberate_session_healthy_at_60pct(self, mock_db):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            ("deliberate-session", now, now),
        )
        # Same 70% ratio, but deliberate mode -> should be warning (not throttled)
        for i in range(10):
            is_self = 1 if i < 7 else 0
            await db.execute(
                "INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, "
                "session_id, is_self_referential, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"Memory {i}", "experience", 5, 0.0, "[]", "deliberate-session", is_self, now, now),
            )
        await db.commit()

        # Register 2 self-awareness tools to enter deliberate mode
        introspection_budget._session_tool_calls.clear()
        introspection_budget.record_tool_call("deliberate-session", "check_alignment")
        introspection_budget.record_tool_call("deliberate-session", "measure_growth")

        budget = await introspection_budget.update_budget("deliberate-session")
        assert budget["status"] == "healthy"  # 70% is below 70% threshold (not >)
        assert budget["mode"] == "deliberate"


# --- Feature 3: Procedural Memory Type ---


class TestProceduralDecay:
    def test_procedure_halflife_3x_longer(self):
        normal = compute_half_life(5)
        procedure = compute_half_life(5, memory_type="procedure")
        assert procedure == pytest.approx(normal * 3.0)

    def test_procedure_halflife_importance_1(self):
        normal = compute_half_life(1)
        procedure = compute_half_life(1, memory_type="procedure")
        assert procedure == pytest.approx(72.0, rel=0.01)  # 24 * 3

    def test_procedure_halflife_importance_10(self):
        procedure = compute_half_life(10, memory_type="procedure")
        normal = compute_half_life(10)
        assert procedure > 1400  # ~1434h
        assert procedure == pytest.approx(normal * 3.0)

    def test_non_procedure_unchanged(self):
        for mtype in ["experience", "fact", "observation", "insight"]:
            assert compute_half_life(5, memory_type=mtype) == compute_half_life(5)

    def test_procedure_decays_slower(self):
        start = "2024-01-01T00:00:00+00:00"
        end = "2024-01-15T00:00:00+00:00"  # 14 days later

        normal_activation = decay_activation(1.0, 5, start, end)
        procedure_activation = decay_activation(1.0, 5, start, end, memory_type="procedure")

        assert procedure_activation > normal_activation


class TestProceduralMemoryType:
    def test_procedure_in_pydantic_model(self):
        from megregore.models import CreateMemoryRequest
        req = CreateMemoryRequest(content="Test procedure", memory_type="procedure")
        assert req.memory_type == "procedure"

    def test_invalid_type_rejected(self):
        from megregore.models import CreateMemoryRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CreateMemoryRequest(content="Test", memory_type="invalid")

    def test_procedure_not_self_referential(self):
        assert introspection_budget.is_self_referential(
            "When delegating to DeepSeek, fix DB patterns", "procedure"
        ) is False


class TestProceduralSurfacingBoost:
    @pytest.mark.asyncio
    async def test_procedure_gets_boosted_score(self, mock_db, mock_embeddings):
        from megregore import surfacing

        db = mock_db
        now = datetime.now(timezone.utc).isoformat()

        # Mock semantic search to return both memories
        async def mock_search(query, limit=20):
            return [(1, 0.8), (2, 0.8)]  # Same similarity

        from megregore import embeddings
        original_search = embeddings.semantic_search
        embeddings.semantic_search = mock_search

        try:
            # Insert a normal memory and a procedure with identical attributes
            await db.execute(
                "INSERT INTO memories (id, content, memory_type, importance, emotional_weight, tags, "
                "activation_level, access_count, is_self_referential, created_at, last_accessed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "Normal memory", "experience", 5, 0.0, "[]", 1.0, 1, 0, now, now),
            )
            await db.execute(
                "INSERT INTO memories (id, content, memory_type, importance, emotional_weight, tags, "
                "activation_level, access_count, is_self_referential, created_at, last_accessed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (2, "Procedure memory", "procedure", 5, 0.0, "[]", 1.0, 1, 0, now, now),
            )
            await db.commit()

            results = await surfacing.surface_relevant("test context", limit=10)
            assert len(results) == 2

            # Procedure should be ranked higher due to 1.5x boost
            procedure_result = [r for r in results if r["memory_type"] == "procedure"][0]
            normal_result = [r for r in results if r["memory_type"] == "experience"][0]
            assert procedure_result["_surfacing_score"] > normal_result["_surfacing_score"]
        finally:
            embeddings.semantic_search = original_search
