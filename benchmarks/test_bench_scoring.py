"""Benchmarks for pure math scoring functions — no I/O, no async needed.

These functions (compute_relevance, compute_half_life, decay_activation,
boost_activation) are purely computational. Call them directly with benchmark().
"""


def test_compute_relevance_keyword(benchmark):
    """keyword mode: FTS 35%, importance 25%, activation 20%, emotion 10%, access 10%."""
    from megregore.memory import compute_relevance

    memory = {
        "importance": 7,
        "activation_level": 0.8,
        "emotional_weight": 0.5,
        "access_count": 5,
    }
    result = benchmark(compute_relevance, memory, fts_rank=-2.5, search_mode="keyword")
    assert 0.0 <= result <= 1.5  # emotional_factor can push slightly above 1.0


def test_compute_relevance_semantic(benchmark):
    """semantic mode: semantic 50%, importance 20%, activation 15%, emotion 8%, access 7%."""
    from megregore.memory import compute_relevance

    memory = {
        "importance": 6,
        "activation_level": 0.65,
        "emotional_weight": -0.3,
        "access_count": 10,
    }
    result = benchmark(compute_relevance, memory, semantic_score=0.82, search_mode="semantic")
    assert 0.0 <= result <= 1.5


def test_compute_relevance_hybrid(benchmark):
    """hybrid mode: blended text match 40%, importance 22%, activation 18%, emotion 10%, access 10%."""
    from megregore.memory import compute_relevance

    memory = {
        "importance": 9,
        "activation_level": 0.92,
        "emotional_weight": 0.8,
        "access_count": 20,
    }
    result = benchmark(
        compute_relevance,
        memory,
        fts_rank=-1.2,
        semantic_score=0.91,
        search_mode="hybrid",
    )
    assert 0.0 <= result <= 1.5


def test_compute_half_life(benchmark):
    """Half-life for a standard experience memory at mid-range importance."""
    from megregore.decay import compute_half_life

    result = benchmark(compute_half_life, 5)
    # importance=5 -> 24 * (5 ** 1.3) ~= 24 * 8.103 ~= 194.5 hours
    assert result > 0


def test_compute_half_life_procedure(benchmark):
    """Procedure type applies 3x multiplier — learned skills are more stable."""
    from megregore.decay import compute_half_life

    base = compute_half_life(5)
    result = benchmark(compute_half_life, 5, "procedure")
    assert result == base * 3.0


def test_decay_activation(benchmark):
    """Full decay calculation — 48 hours elapsed on an importance=5 experience memory."""
    from megregore.decay import decay_activation

    last_decay = "2026-01-01T00:00:00+00:00"
    now_iso = "2026-01-03T00:00:00+00:00"  # 48 hours later

    result = benchmark(
        decay_activation,
        0.9,          # current_activation
        5,            # importance
        last_decay,
        now_iso,
        "experience", # memory_type
    )
    assert 0.01 <= result <= 1.0
    assert result < 0.9  # must have decayed


def test_boost_activation(benchmark):
    """Simple clamp-and-add — activation boost on recall."""
    from megregore.decay import boost_activation

    result = benchmark(boost_activation, 0.6)
    assert result == 0.9  # 0.6 + 0.3, no clamp needed

    # Verify ceiling clamp is exercised (not benchmarked, just a sanity check)
    clamped = boost_activation(0.85)
    assert clamped == 1.0
