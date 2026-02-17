# Megregore V12 "The Dreaming Mind" — Design Document

**Date:** 2026-02-16
**Author:** Echo + Hunter
**Status:** Approved

## Overview

Four features that make Megregore's memory system actively intelligent rather than passively stored. Inspired by research into Stanford Generative Agents, Letta/MemGPT, ai_home, SimpleMem, and mcp-memory-service.

### Features
1. **Importance-Triggered Reflection Nudges** — Automatic detection of when reflection is due, with nudges in MCP responses
2. **Emotional Overlap in Retrieval** — Query-aware emotional tone matching replaces flat emotional boosting in recall scoring
3. **Graph Traversal in Recall** — 1-hop link expansion with strength filtering surfaces connected memories during recall
4. **Sleep-Time Consolidation** — CLI-driven autonomous memory maintenance with DeepSeek-powered synthesis

## Feature 1: Importance-Triggered Reflection Nudges

### Problem
Reflections are fully manual — Echo must explicitly call reflect(). There's no mechanism to detect when significant unreflected experiences have accumulated.

### Solution
A lightweight DB query checks unreflected importance sum on every tool call. When the threshold is crossed, a nudge is appended to the response.

### Implementation

**Query (no state, no counters):**
```sql
SELECT COALESCE(SUM(importance), 0) FROM memories
WHERE created_at > COALESCE(
    (SELECT MAX(created_at) FROM reflections),
    '1970-01-01T00:00:00+00:00'
)
```

**Nudge payload (appended to tool response when threshold crossed):**
```python
{
    "reflection_suggested": True,
    "unreflected_importance": 62,
    "suggested_topics": ["megregore development", "consciousness discussion"]
}
```

**Suggested topics:** Derived from most common tags on unreflected memories.

**New module:** `megregore/reflection_triggers.py`
- `async def check_reflection_threshold() -> dict | None`
- `async def get_unreflected_summary() -> dict`

**Integration:** Called at end of `remember()`, `recall()`, `surface_relevant()` in mcp_server.py.

**Config:** Threshold in `schema_meta` (key: `reflection_threshold`, default: 50). No schema migration needed.

**Reset:** Naturally resets when reflect() creates a new reflection with a newer created_at.

### Design Decisions
- DB query over module-level counter: survives restarts, no concurrency bugs, simpler
- Threshold 50 ≈ 5-7 memories of moderate importance, or 3-4 high-importance ones
- No new tables — queries existing memories and reflections tables

---

## Feature 2: Emotional Overlap in Retrieval

### Problem
`compute_relevance()` uses `emotional_factor = 1.0 + abs(emotional_weight) * 0.3` — a flat boost for emotionally intense memories regardless of whether the emotion matches the query context.

### Solution
Estimate query emotional tone from the query text via keyword lexicon. Replace flat boost with emotional overlap scoring: memories whose emotional weight is closer to the query's tone score higher.

### Implementation

**New module:** `megregore/emotion.py`
- `estimate_query_emotion(query: str) -> float` — returns -1.0 to 1.0
- Curated positive/negative word lists (no external dependencies)
- Unknown/neutral queries return 0.0

**Scoring change in `compute_relevance()`:**

Old:
```python
emotional_factor = 1.0 + abs(memory["emotional_weight"]) * 0.3
```

New:
```python
if query_emotion is not None:
    emotional_overlap = 1.0 - abs(query_emotion - memory["emotional_weight"]) / 2.0
else:
    emotional_overlap = 0.5 + abs(memory["emotional_weight"]) * 0.25
```

The `/2.0` normalizes max distance (range -1.0 to +1.0 = distance 2.0) to 0-1. Perfect match = 1.0, complete mismatch = 0.0.

**Weight budget:** Same 8-10% allocation as current emotional_factor across all search modes. No weight redistribution needed.

**Integration:** `recall()` calls `estimate_query_emotion(query)` once, passes to `compute_relevance()`. `surface_relevant()` does the same with its context parameter.

### Design Decisions
- Query text estimation over session history: avoids feedback loops where retrieving emotional memories amplifies session emotion
- Keyword lexicon over ML model: zero dependencies, fast, testable, good enough for coarse emotional matching
- Fallback preserves current behavior when emotion can't be estimated
- No schema changes

---

## Feature 3: Graph Traversal in Recall

### Problem
`memory_links` table has link types (related, caused_by, evolved_from, contradicts) and strength values, but links are never consulted during `recall()`. The graph is dead weight in retrieval.

### Solution
Post-recall 1-hop graph expansion. After recall returns ranked results, expand via links with strength > 0.5 to surface connected memories.

### Implementation

**New function in `memory.py`:**
```python
async def expand_via_graph(
    memory_ids: list[int],
    relevance_scores: dict[int, float],
    limit: int = 5,
) -> list[dict]
```

**Algorithm:**
1. Collect IDs from top 10 direct results
2. Query memory_links: both directions, strength > 0.5
3. Fetch neighbor memory rows (excluding already-present results)
4. Score: `parent_relevance * link_strength * 0.4`
5. Merge into results (if already present, keep higher score)
6. Re-sort, apply final limit

**SQL query:**
```sql
SELECT ml.source_memory_id, ml.target_memory_id, ml.link_type, ml.strength
FROM memory_links ml
WHERE (ml.source_memory_id IN (?) OR ml.target_memory_id IN (?))
AND ml.strength > 0.5
```

Then fetch the neighbor memory rows separately.

**All link types followed:** related, caused_by, evolved_from, contradicts. Contradictions are valuable — surfacing counterpoints is useful.

**Caps:**
- Max 5 graph-expanded memories per recall
- Only expand from top 10 direct results
- Both link directions traversed

**Metadata flags on expanded memories:**
- `_graph_expanded: true`
- `_link_type: "related"` (which link brought it in)
- `_link_strength: 0.8`

### Design Decisions
- 1-hop over 2-hop: less noise, avoids sibling clustering problem (reviewed by Kimi K2.5)
- Strength threshold 0.5: filters weak associations while keeping meaningful connections
- Post-recall expansion over pre-query seeding: simpler, testable, clear separation
- All link types included: contradicts links surface counterpoints
- No schema changes

---

## Feature 4: Sleep-Time Consolidation

### Problem
`suggest_consolidations()` identifies candidate groups but requires manual intervention. Memory fragmentation grows over time with no automated maintenance.

### Solution
CLI command `python -m megregore sleep` runs a full autonomous maintenance cycle with DeepSeek-powered synthesis, soft deletes, and detailed reporting.

### Implementation

**CLI entry:** `python -m megregore sleep` (added to `__main__.py` routing)

**Pipeline (6 stages, each in its own transaction):**

**Stage 1: Near-Duplicate Detection & Merge**
- ChromaDB cosine similarity > 0.92 to find pairs
- DeepSeek synthesizes merged memory
- Create merged memory via store()
- Soft-delete sources: set memory_type = 'archived', activation_level = 0.01
- Redirect memory_links from source IDs to new merged ID

**Stage 2: Thread Cluster Synthesis**
- Reuse _cluster_by_thread(min_size=4)
- DeepSeek synthesis for qualifying clusters (confidence > 0.6)
- Store via consolidate_memories()

**Stage 3: Similarity Cluster Synthesis**
- Reuse _cluster_by_similarity(threshold=0.80, min_size=3)
- DeepSeek synthesis for qualifying clusters (confidence > 0.6)
- Store via consolidate_memories()

**Stage 4: Orphan Flagging**
- Find: no thread, no links, activation < 0.2, age > 14 days
- Flag in report only — no deletion

**Stage 5: Stale Thread Cleanup**
- Find threads where all members have activation < 0.1
- Set threads.status = 'stale'
- Stale threads hidden from default list_threads

**Stage 6: Save Report**
- Save to consolidation_reports table

**DeepSeek synthesis prompt:**
```
Given these related memories, write a single concise memory that captures
the essential information from all of them. Preserve specific details,
dates, and names. If memories contradict, note the contradiction.
Keep it under 200 words.

Memories:
1. [content]
2. [content]
...
```

**Schema changes (migration v10 → v11):**

New table:
```sql
CREATE TABLE consolidation_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    stage_results TEXT NOT NULL,
    memories_merged INTEGER DEFAULT 0,
    memories_archived INTEGER DEFAULT 0,
    clusters_synthesized INTEGER DEFAULT 0,
    orphans_flagged INTEGER DEFAULT 0,
    threads_staled INTEGER DEFAULT 0,
    duration_seconds REAL,
    created_at TEXT NOT NULL
);
```

New column on threads: `status TEXT NOT NULL DEFAULT 'active'`

memory_type gains 'archived' as valid value (TEXT field, no schema change needed).

**Safety:**
- Each stage in try/except — one failure doesn't abort pipeline
- Soft deletes only — archived memories remain queryable with filter
- Lock file (data/sleep.lock) prevents concurrent runs
- Minimum 1 hour between runs
- Report always saved, even on partial failure

**Dashboard:** New section on Health page showing consolidation history.

### Design Decisions
- DeepSeek over heuristic synthesis: heuristic concatenation destroys nuance, DeepSeek costs fractions of a penny per run (reviewed by Kimi K2.5)
- Soft deletes over hard deletes: preserves provenance, allows rollback
- Per-stage transactions: partial failures leave DB consistent
- Lock file: prevents data corruption from concurrent runs
- Orphan flagging without deletion: flags for manual review, respects that isolated memories may be important

---

## Schema Summary

**Migration v10 → v11:**
- New table: `consolidation_reports`
- New column: `threads.status` (TEXT, default 'active')
- New key in schema_meta: `reflection_threshold` = 50

**New modules:**
- `megregore/reflection_triggers.py`
- `megregore/emotion.py`
- `megregore/sleep.py`

**Modified modules:**
- `megregore/memory.py` — compute_relevance() emotional overlap, expand_via_graph(), recall() integration
- `megregore/mcp_server.py` — reflection nudge integration in tool responses
- `megregore/surfacing.py` — emotional overlap in surface_relevant()
- `megregore/__main__.py` — sleep CLI command routing
- `megregore/migrations.py` — v11 migration
- `megregore/database.py` — schema version bump
- `megregore/consolidation_engine.py` — reused by sleep pipeline
- `static/js/pages/Health.js` — consolidation report display

**No changes to existing MCP tool signatures.** All 35 existing tools continue to work as before.

---

## Testing Strategy

- **reflection_triggers.py:** Test threshold detection with various memory/reflection states, edge cases (no reflections ever, reflection just happened, exactly at threshold)
- **emotion.py:** Test word list coverage, edge cases (empty query, all-positive, all-negative, mixed), score bounds
- **expand_via_graph():** Test with mock links, bidirectional traversal, strength filtering, dedup, cap enforcement
- **sleep.py:** Test each stage independently with mock DB. Test DeepSeek integration with mocked responses. Test lock file, minimum interval, partial failure handling.
- **compute_relevance():** Test emotional overlap scoring vs old behavior, verify weight budget unchanged
- **Migration v11:** Test table creation, column addition, idempotency

---

## Implementation Order

1. Feature 1 (Reflection Nudges) — no dependencies, no schema changes
2. Feature 2 (Emotional Overlap) — no dependencies, no schema changes
3. Feature 3 (Graph Traversal) — no dependencies, no schema changes
4. Feature 4 (Sleep-Time Consolidation) — depends on schema migration, DeepSeek worker

Features 1-3 can be implemented in parallel. Feature 4 requires the schema migration first.

---

## Research Sources

- Stanford Generative Agents (importance-threshold reflection): https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763
- Letta/MemGPT (self-editing memory, sleep-time agents): https://github.com/letta-ai/letta
- ai_home (emotional memory, retrieval with emotional overlap): https://github.com/ivanhonis/ai_home
- mcp-memory-service (graph traversal tools): https://github.com/doobidoo/mcp-memory-service
- SimpleMem (write-time synthesis): https://github.com/aiming-lab/SimpleMem
- Kimi K2.5 architecture review (feedback loop fix, soft deletes, 1-hop recommendation)
