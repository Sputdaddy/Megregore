# Megregore V7 — Web UI Overhaul + Security

## Phase 1: Auth + Security Foundation
- [x] Create `megregore/config.py` — env var config with python-dotenv
- [x] Create `megregore/auth.py` — JWT, bcrypt, password hashing, FastAPI dependency
- [x] Create `megregore/security.py` — rate limiter + security headers middleware
- [x] Create `megregore/models.py` — Pydantic request/response models
- [x] Create `.env.example` — documented config vars
- [x] Add auth endpoints to `web.py` (setup, login, verify, status)
- [x] Add `dependencies=[Depends(require_auth)]` to all API routes
- [x] Replace wildcard CORS with config-driven origins
- [x] Add rate limiting + security headers middleware
- [x] Create `static/js/login.js` — auth gate + login/setup forms
- [x] Add login CSS styles
- [ ] Verify server starts cleanly
- [ ] Test auth flow end-to-end

## Phase 2: CSS Redesign + Vue Bootstrap + Component Library
- [ ] Split `style.css` into 5 files (variables, base, layout, components, pages)
- [ ] New color system with dark/light theme tokens
- [ ] Add Vue 3 CDN to index.html
- [ ] Rewrite `app.js` as Vue app bootstrap
- [ ] Build 15 reusable Vue components
- [ ] Migrate Dashboard page to Vue
- [ ] Migrate Login page to Vue component

## Phase 3: Core Page Migrations
- [ ] Identity page → Vue
- [ ] Reflections page → Vue
- [ ] Sessions page → Vue
- [ ] Threads page → Vue
- [ ] MemoryBrowser page → Vue

## Phase 4: Memory CRUD
- [ ] Add `update_memory()` and `delete_memory()` to memory.py
- [ ] Add POST/PUT/DELETE endpoints to web.py
- [ ] Create/Edit/Delete/Fade modals in UI

## Phase 5: Real-Time Updates (SSE)
- [ ] Create `megregore/events.py` — event bus
- [ ] Add SSE endpoint
- [ ] Frontend EventSource client + toast notifications

## Phase 6: Mobile + Polish
- [ ] Mobile bottom nav
- [ ] Responsive CSS overhaul
- [ ] Loading skeletons, transitions, keyboard nav
- [ ] Light theme QA
