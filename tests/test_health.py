import pytest
from datetime import datetime, timedelta, timezone
from megregore.health import run_health_check, _find_anomalies, _find_orphans, _find_stale_threads

pytestmark = pytest.mark.asyncio


class TestRunHealthCheck:
    async def test_returns_complete_report(self, mock_db, mock_embeddings, sample_memories):
        report = await run_health_check()
        assert report["status"] == "completed"
        assert "summary" in report
        assert "near_duplicates" in report
        assert "anomalies" in report
        assert "orphans" in report
        assert "stale_threads" in report

    async def test_empty_database(self, mock_db, mock_embeddings):
        report = await run_health_check()
        assert report["status"] == "completed"
        assert report["summary"]["total_issues"] == 0


class TestFindAnomalies:
    async def test_finds_forgotten_important(self, mock_db, mock_embeddings, sample_memories):
        anomalies = await _find_anomalies()
        forgotten = [a for a in anomalies if a["anomaly_type"] == "forgotten_important"]
        assert len(forgotten) >= 1

    async def test_finds_undervalued(self, mock_db, mock_embeddings, sample_memories):
        anomalies = await _find_anomalies()
        undervalued = [a for a in anomalies if a["anomaly_type"] == "undervalued"]
        assert len(undervalued) >= 1

    async def test_severity_is_bounded(self, mock_db, mock_embeddings, sample_memories):
        anomalies = await _find_anomalies()
        for a in anomalies:
            assert 0.0 <= a["severity"] <= 1.0


class TestFindOrphans:
    async def test_finds_old_unlinked_memories(self, mock_db, mock_embeddings):
        """Orphans are memories older than 7 days with no links and no recent access."""
        db = mock_db
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        await db.execute(
            """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source,
               activation_level, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Old orphan memory", "experience", 5, 0.0, '["test"]', "conversation",
             0.5, old_date, old_date, 0)
        )
        await db.commit()
        orphans = await _find_orphans()
        assert len(orphans) >= 1
        assert any("Old orphan" in o["content"] for o in orphans)

    async def test_recent_memories_not_orphaned(self, mock_db, mock_embeddings, sample_memories):
        """Memories created less than 7 days ago should not be orphans."""
        orphans = await _find_orphans()
        # sample_memories are all created "now", so none should be orphans
        assert len(orphans) == 0

    async def test_orphan_has_required_fields(self, mock_db, mock_embeddings):
        db = mock_db
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        await db.execute(
            """INSERT INTO memories (content, memory_type, importance, emotional_weight, tags, source,
               activation_level, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Field test orphan", "fact", 3, 0.0, '["test"]', "conversation",
             0.3, old_date, old_date, 0)
        )
        await db.commit()
        orphans = await _find_orphans()
        assert len(orphans) >= 1
        orphan = orphans[0]
        assert "memory_id" in orphan or "id" in orphan
        assert "content" in orphan
        assert "memory_type" in orphan
        assert "importance" in orphan
        assert "created_at" in orphan


class TestFindStaleThreads:
    async def test_finds_empty_threads(self, mock_db, mock_embeddings):
        db = mock_db
        now = "2024-01-01T00:00:00+00:00"
        await db.execute(
            "INSERT INTO threads (title, created_at, last_active, memory_count) VALUES (?, ?, ?, ?)",
            ("Empty thread", now, now, 0)
        )
        await db.commit()
        stale = await _find_stale_threads()
        assert len(stale) >= 1
        assert stale[0]["memory_count"] == 0

    async def test_healthy_thread_not_stale(self, mock_db, mock_embeddings):
        db = mock_db
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO threads (title, created_at, last_active, memory_count) VALUES (?, ?, ?, ?)",
            ("Active thread", now, now, 5)
        )
        await db.commit()
        stale = await _find_stale_threads()
        assert not any(t["title"] == "Active thread" for t in stale)


class TestHealthReportStructure:
    """Verify the health report matches what the frontend Health.js expects."""

    async def test_summary_has_all_keys(self, mock_db, mock_embeddings, sample_memories):
        report = await run_health_check()
        summary = report["summary"]
        assert "total_issues" in summary
        assert "near_duplicates" in summary
        assert "anomalies" in summary
        assert "orphans" in summary
        assert "stale_threads" in summary

    async def test_summary_counts_match_detail_lengths(self, mock_db, mock_embeddings, sample_memories):
        report = await run_health_check()
        summary = report["summary"]
        assert summary["near_duplicates"] == len(report["near_duplicates"])
        assert summary["anomalies"] == len(report["anomalies"])
        assert summary["orphans"] == len(report["orphans"])
        assert summary["stale_threads"] == len(report["stale_threads"])

    async def test_anomaly_has_fields_for_frontend(self, mock_db, mock_embeddings, sample_memories):
        report = await run_health_check()
        if report["anomalies"]:
            anom = report["anomalies"][0]
            assert "anomaly_type" in anom
            assert "memory_id" in anom
            assert "content" in anom
            assert "importance" in anom
            assert "activation_level" in anom
            assert "severity" in anom
