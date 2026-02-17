import pytest
from megregore.consolidation_engine import (
    find_consolidation_candidates, _cluster_by_thread, _score_candidate_group
)


class TestScoreCandidateGroup:
    def test_high_similarity_same_thread(self):
        memories = [
            {"importance": 7, "activation_level": 0.6, "tags": ["python", "code"]},
            {"importance": 6, "activation_level": 0.5, "tags": ["python", "code"]},
            {"importance": 8, "activation_level": 0.7, "tags": ["python"]},
        ]
        score = _score_candidate_group(memories, same_thread=True, avg_similarity=0.85)
        assert 0.5 < score < 1.0

    def test_low_similarity_no_thread(self):
        memories = [
            {"importance": 3, "activation_level": 0.9, "tags": ["a"]},
            {"importance": 4, "activation_level": 0.8, "tags": ["b"]},
            {"importance": 2, "activation_level": 0.7, "tags": ["c"]},
        ]
        score = _score_candidate_group(memories, same_thread=False, avg_similarity=0.3)
        assert score < 0.4

    def test_empty_group_returns_zero(self):
        assert _score_candidate_group([], same_thread=False) == 0.0

    def test_score_bounded_0_1(self):
        memories = [{"importance": 10, "activation_level": 0.01, "tags": ["a", "b"]}] * 4
        score = _score_candidate_group(memories, same_thread=True, avg_similarity=1.0)
        assert 0.0 <= score <= 1.0


class TestClusterByThread:
    async def test_finds_thread_groups(self, mock_db, mock_embeddings):
        db = mock_db
        now = "2024-01-01T00:00:00+00:00"

        cursor = await db.execute(
            "INSERT INTO threads (title, created_at, last_active, memory_count) VALUES (?, ?, ?, ?)",
            ("Test Thread", now, now, 3)
        )
        thread_id = cursor.lastrowid

        for i in range(3):
            await db.execute(
                """INSERT INTO memories (content, memory_type, importance, tags, thread_id, activation_level, last_activation_decay, created_at, last_accessed)
                VALUES (?, 'fact', 5, '["test"]', ?, 0.8, ?, ?, ?)""",
                (f"Memory {i}", thread_id, now, now, now)
            )
        await db.commit()

        groups = await _cluster_by_thread(min_size=3)
        assert len(groups) >= 1
        assert len(groups[0]["memory_ids"]) == 3


class TestFindConsolidationCandidates:
    async def test_empty_database(self, mock_db, mock_embeddings):
        candidates = await find_consolidation_candidates()
        assert candidates == []
