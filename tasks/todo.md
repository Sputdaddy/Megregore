# Megregore V5 — Memory Intelligence Build Plan

## Phase 1: Schema Migration (v5 → v6)
- [x] Add `source` column to `memory_links` table
- [x] Add `migrate_v5_to_v6()` to migrations.py
- [x] Update database.py SCHEMA_VERSION to 6
- [x] Update `link_memories()` to accept `source` param

## Phase 2: Auto-Link Inference
- [x] Create `auto_linker.py` — `infer_links()`, `suggest_links()`, `_find_unlinked_pairs()`
- [x] Add MCP tool `suggest_links_tool`
- [x] Add lifespan auto-link call in mcp_server.py
- [x] Add web endpoint `GET /api/health/suggested-links`

## Phase 3: Memory Health & Hygiene
- [x] Create `health.py` — `run_health_check()`, `_find_near_duplicates()`, `_find_anomalies()`, `_find_orphans()`, `_find_stale_threads()`
- [x] Add MCP tool `memory_health`
- [x] Add web endpoint `GET /api/health`
- [x] Add Health page to web UI (health.js + nav entry)

## Phase 4: Auto-Consolidation Engine
- [x] Create `consolidation_engine.py` — `find_consolidation_candidates()`, `_cluster_by_thread()`, `_cluster_by_similarity()`, `_score_candidate_group()`
- [x] Add MCP tool `suggest_consolidations`
- [x] Add web endpoint `GET /api/health/consolidation-candidates`

## Phase 5: Test Suite
- [ ] Create `tests/conftest.py` with fixtures
- [ ] Create test files for all modules
- [ ] Run pytest — all tests pass
- [ ] Verify MCP server starts cleanly

## Phase 6: Integration & Verification
- [ ] Restart MCP server, verify startup sequence
- [ ] Test all 17 MCP tools
- [ ] Verify web dashboard Health page
- [ ] Calculate token savings from delegation

---

## Delegation Strategy
- **DeepSeek**: Algorithm design ($0.002 + $0.0015 = $0.0035 total)
- **Sonnet 4.5 agents**: Module implementation, UI, tests
- **Opus**: Architecture, integration, review

## Files Modified
- `megregore/database.py` — SCHEMA_VERSION 5→6
- `megregore/migrations.py` — added `migrate_v5_to_v6()`
- `megregore/mcp_server.py` — 3 new tools, lifespan auto-link
- `megregore/memory.py` — `link_memories()` source param
- `megregore/web.py` — 3 new API endpoints, new imports
- `static/index.html` — Health nav entry + script tag

## Files Created
- `megregore/auto_linker.py`
- `megregore/health.py`
- `megregore/consolidation_engine.py`
- `static/js/health.js`
- `tests/conftest.py`
- `tests/test_decay.py`
- `tests/test_memory.py`
- `tests/test_health.py`
- `tests/test_auto_linker.py`
- `tests/test_consolidation.py`
- `tests/test_threads.py`
- `tests/test_analytics.py`
- `pytest.ini`
