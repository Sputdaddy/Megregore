import pytest
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
