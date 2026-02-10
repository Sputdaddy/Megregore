# Megregore Test Suite

Comprehensive pytest test suite for the Megregore memory system.

## Setup

Install test dependencies:

```bash
pip install -r requirements-dev.txt
```

## Running Tests

Run all tests:
```bash
pytest
```

Run a specific test file:
```bash
pytest tests/test_decay.py
```

Run a specific test class:
```bash
pytest tests/test_memory.py::TestStore
```

Run a specific test:
```bash
pytest tests/test_memory.py::TestStore::test_basic_store
```

Run with verbose output:
```bash
pytest -v
```

Run with coverage:
```bash
pytest --cov=megregore --cov-report=html
```

## Test Structure

### `conftest.py`
Shared fixtures for all tests:
- `db`: In-memory SQLite database with full schema
- `mock_db`: Patches `database.get_connection()` to use test database
- `mock_embeddings`: Mocks embeddings module (no sentence-transformers dependency)
- `sample_memories`: Pre-populated test data

### `test_decay.py`
Tests the pure math functions in `megregore.decay`:
- `compute_half_life()`: Exponential scaling by importance
- `decay_activation()`: Time-based activation decay
- `boost_activation()`: Access-triggered activation boost

### `test_memory.py`
Tests CRUD operations in `megregore.memory`:
- `store()`: Create new memories
- `get()`: Retrieve by ID
- `fade()`: Reduce importance
- `link_memories()`: Create relationships
- `consolidate_memories()`: Synthesize multiple memories

### `test_health.py`
Tests memory health checks in `megregore.health`:
- `run_health_check()`: Full system scan
- `_find_anomalies()`: Detect inconsistencies
- `_find_stale_threads()`: Identify empty threads

### `test_auto_linker.py`
Tests automatic link inference in `megregore.auto_linker`:
- `infer_links()`: Batch link creation
- `suggest_links()`: Link recommendations
- `_find_unlinked_pairs()`: Candidate detection

### `test_consolidation.py`
Tests consolidation engine in `megregore.consolidation_engine`:
- `_score_candidate_group()`: Pure scoring function
- `_cluster_by_thread()`: Thread-based grouping
- `find_consolidation_candidates()`: Full detection

### `test_threads.py`
Tests threading system in `megregore.threads`:
- `create_thread()`: Thread creation
- `assign_to_thread()`: Memory assignment
- `list_threads()`: Thread listing

### `test_analytics.py`
Tests analytics in `megregore.analytics`:
- `log_access()`: Access logging
- `compute_analytics()`: Memory statistics
- `get_top_accessed()`: Most-accessed memories

## Test Isolation

All tests use in-memory SQLite databases that are created fresh for each test. The `mock_db` fixture patches `database.get_connection()` to return the test database, ensuring complete isolation from the production database.

## Mocking Strategy

The test suite mocks the embeddings module to avoid:
- Loading large sentence-transformer models
- Network dependencies
- Slow embedding computation

Tests can override the mock by using `monkeypatch` to inject specific behavior.

## Writing New Tests

Follow these conventions:

1. Use `pytestmark = pytest.mark.asyncio` for async tests
2. Use descriptive test names: `test_<what>_<scenario>`
3. Group related tests in classes: `class TestFunctionName`
4. Use fixtures: `mock_db`, `mock_embeddings`, `sample_memories`
5. Test one thing per test function
6. Prefer parametrized tests for similar cases

Example:
```python
import pytest
from megregore.memory import store

pytestmark = pytest.mark.asyncio

class TestStore:
    async def test_creates_memory_with_default_activation(self, mock_db, mock_embeddings):
        result = await store(content="Test", session_id="s1")
        assert result["activation_level"] == 1.0
```

## Continuous Integration

The test suite is designed to run in CI environments without external dependencies. All database operations use in-memory SQLite, and embeddings are mocked.
