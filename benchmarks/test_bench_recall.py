"""Benchmarks for the recall hot path — FTS5 + scoring via keyword mode."""


def test_recall_keyword(benchmark, seeded_db, mock_bench_embeddings):
    """Basic keyword recall against seeded content."""
    from megregore.memory import recall
    from benchmarks.conftest import run_async

    def do_recall():
        return run_async(recall("memory systems", limit=20, search_mode="keyword", expand_graph=False))

    benchmark(do_recall)


def test_recall_with_type_filter(benchmark, seeded_db, mock_bench_embeddings):
    """Keyword recall filtered to a single memory_type."""
    from megregore.memory import recall
    from benchmarks.conftest import run_async

    def do_recall():
        return run_async(
            recall(
                "memory systems",
                limit=20,
                memory_type="experience",
                search_mode="keyword",
                expand_graph=False,
            )
        )

    benchmark(do_recall)


def test_recall_with_tags_filter(benchmark, seeded_db, mock_bench_embeddings):
    """Keyword recall filtered by a tag present in the seeded pool."""
    from megregore.memory import recall
    from benchmarks.conftest import run_async

    def do_recall():
        return run_async(
            recall(
                "memory systems",
                limit=20,
                tags_filter=["python"],
                search_mode="keyword",
                expand_graph=False,
            )
        )

    benchmark(do_recall)


def test_recall_no_graph_expansion(benchmark, seeded_db, mock_bench_embeddings):
    """Keyword recall with graph expansion explicitly disabled — isolates FTS5 + scoring."""
    from megregore.memory import recall
    from benchmarks.conftest import run_async

    def do_recall():
        return run_async(
            recall(
                "identity evolution",
                limit=20,
                search_mode="keyword",
                expand_graph=False,
            )
        )

    benchmark(do_recall)
