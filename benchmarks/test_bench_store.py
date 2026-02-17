"""Benchmarks for the memory store write path."""

import pytest


def test_store_minimal(benchmark, mock_bench_db, mock_bench_embeddings):
    """Benchmark store() with content only — bare minimum path."""
    from megregore.memory import store
    from benchmarks.conftest import run_async

    counter = [0]

    def do_store():
        counter[0] += 1
        return run_async(store(content=f"Benchmark memory {counter[0]}"))

    benchmark(do_store)


def test_store_full(benchmark, mock_bench_db, mock_bench_embeddings):
    """Benchmark store() with all fields populated — full write path."""
    from megregore.memory import store
    from benchmarks.conftest import run_async

    counter = [0]

    def do_store():
        counter[0] += 1
        return run_async(
            store(
                content=f"Full benchmark memory {counter[0]}",
                memory_type="reflection",
                importance=8,
                emotional_weight=0.5,
                tags=["benchmark", "performance", "testing"],
                source="benchmark",
                context=f"Benchmark run iteration {counter[0]}",
                session_id="bench-session-001",
                thread_id=1,
            )
        )

    benchmark(do_store)
