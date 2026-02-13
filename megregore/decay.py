"""Activation decay engine for Megregore V4. Pure math, no I/O."""

import math
from datetime import datetime


def compute_half_life(importance: int, memory_type: str = "experience") -> float:
    """
    Compute half-life in hours, scaled by importance level (1-10).

    Higher importance memories decay more slowly. Uses exponential scaling
    to give meaningful differences across the importance range.
    Procedural memories decay 3x slower — learned skills are more stable.

    Args:
        importance: Memory importance level (1-10).
        memory_type: Memory type. "procedure" gets 3x multiplier.

    Returns:
        Half-life in hours. importance=1 yields ~24h, importance=10 yields ~478h.
        Procedures: importance=1 yields ~72h, importance=10 yields ~1434h.
    """
    base = 24.0 * (importance ** 1.3)
    if memory_type == "procedure":
        return base * 3.0
    return base


def decay_activation(
    current_activation: float,
    importance: int,
    last_decay_at: str,
    now_iso: str,
    memory_type: str = "experience",
) -> float:
    """
    Apply exponential decay to activation based on time elapsed.

    Simulates natural decay of memory activation over time using exponential
    decay curve with half-life determined by importance and memory type.

    Args:
        current_activation: Current activation value (0.01-1.0).
        importance: Memory importance level (1-10).
        last_decay_at: ISO-format timestamp of last decay application.
        now_iso: Current time as ISO-format timestamp.
        memory_type: Memory type. "procedure" decays 3x slower.

    Returns:
        Decayed activation value, clamped to [0.01, 1.0] and rounded to 4 decimals.
    """
    then = datetime.fromisoformat(last_decay_at)
    now = datetime.fromisoformat(now_iso)

    hours_elapsed = (now - then).total_seconds() / 3600.0

    if hours_elapsed <= 0:
        return current_activation

    half_life = compute_half_life(importance, memory_type)
    lambda_decay = 0.693 / half_life
    decayed = current_activation * math.exp(-lambda_decay * hours_elapsed)

    return max(0.01, min(1.0, round(decayed, 4)))


def boost_activation(current_activation: float, boost_amount: float = 0.3) -> float:
    """
    Boost activation by a fixed amount, clamped to maximum.

    Increases activation when a memory is accessed or reinforced. Prevents
    over-saturation by clamping to 1.0.

    Args:
        current_activation: Current activation value (0.01-1.0).
        boost_amount: Amount to increase activation (default 0.3).

    Returns:
        Boosted activation value, clamped to [0.0, 1.0] and rounded to 4 decimals.
    """
    return min(1.0, round(current_activation + boost_amount, 4))
