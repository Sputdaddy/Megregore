"""Benchmarks for apply_activation_decay() — the startup bottleneck."""

import pytest


def test_apply_activation_decay(benchmark, seeded_db, mock_bench_embeddings):
    """
    Benchmark apply_activation_decay() at 3 scales: 10, 100, 500 memories.

    seeded_db is parameterized by memory_count (10/100/500), so this single
    benchmark function runs three separate benchmark cases automatically.
    """
    from megregore.memory import apply_activation_decay
    from benchmarks.conftest import run_async

    def do_decay():
        return run_async(apply_activation_decay())

    benchmark(do_decay)
