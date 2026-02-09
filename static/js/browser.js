/* ============================================================
   Megregore — Memory Browser Page
   ============================================================ */

(() => {

    // --- State ---
    let state = {
        memories: [],
        total: 0,
        offset: 0,
        limit: 20,
        memoryType: '',
        sortBy: 'created_at',
        sortOrder: 'desc',
        searchQuery: '',
        expandedId: null,
        linkedCache: {},
    };

    function resetPagination() {
        state.offset = 0;
    }

    // --- Data Loading ---
    async function loadMemories() {
        if (state.searchQuery.trim()) {
            const data = await App.api('/memories/search', {
                q: state.searchQuery,
                limit: state.limit,
                memory_type: state.memoryType || null,
            });
            state.memories = data.memories || [];
            state.total = data.count || state.memories.length;
        } else {
            const data = await App.api('/memories', {
                limit: state.limit,
                offset: state.offset,
                memory_type: state.memoryType || null,
                sort_by: state.sortBy,
                sort_order: state.sortOrder,
            });
            state.memories = data.memories || [];
            state.total = data.total || 0;
        }
    }

    async function loadLinked(memoryId) {
        if (state.linkedCache[memoryId]) return state.linkedCache[memoryId];
        try {
            const data = await App.api(`/memories/${memoryId}`);
            const linked = data.linked || [];
            state.linkedCache[memoryId] = linked;
            return linked;
        } catch (e) {
            return [];
        }
    }


    // --- Render ---
    function renderMemoryCard(m) {
        const isExpanded = state.expandedId === m.id;
        const content = isExpanded ? m.content : App.truncateText(m.content, 200);
        const needsExpand = m.content && m.content.length > 200;

        return `<div class="card memory-card ${isExpanded ? 'expanded' : ''}" data-id="${m.id}">
            <div class="card-header">
                <div class="flex items-center gap-sm">
                    ${App.typeBadge(m.memory_type)}
                    ${App.emotionalIndicator(m.emotional_weight)}
                </div>
                ${App.importanceDots(m.importance)}
            </div>
            <div class="card-content ${isExpanded ? '' : 'truncated'}">${App.escapeHtml(content)}</div>
            ${needsExpand ? `<button class="expand-btn" data-expand="${m.id}">${isExpanded ? 'Show less' : 'Show more'}</button>` : ''}
            <div class="card-meta">
                ${App.tagPills(m.tags)}
                <span class="card-meta-item muted">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                    ${App.formatDate(m.created_at)}
                </span>
                <span class="card-meta-item muted mono text-xs">views: ${m.access_count || 0}</span>
                ${App.activationBar(m.activation_level)}
                ${m.thread_id ? `<span class="thread-badge">Thread #${m.thread_id}</span>` : ''}
            </div>
            <div class="memory-detail" id="detail-${m.id}">
                <div class="linked-label">Linked Memories</div>
                <div id="linked-${m.id}">
                    <div class="loading" style="padding:16px 0;"><div class="spinner"></div></div>
                </div>
            </div>
        </div>`;
    }

    function renderList() {
        const container = document.getElementById('memory-list');
        if (!container) return;

        if (state.memories.length === 0) {
            if (state.searchQuery.trim()) {
                container.innerHTML = App.emptyState(
                    'No results found',
                    `No memories matched "${state.searchQuery}". Try a different search term.`
                );
            } else {
                container.innerHTML = App.emptyState(
                    'No memories yet',
                    'Echo has not formed any memories yet. They will appear here as they are created through conversation.'
                );
            }
            renderPagination();
            return;
        }

        container.innerHTML = state.memories.map(m => renderMemoryCard(m)).join('');
        renderPagination();
    }

    function renderPagination() {
        const container = document.getElementById('memory-pagination');
        if (!container) return;

        // Don't show pagination for search results
        if (state.searchQuery.trim()) {
            container.innerHTML = `<div class="pagination">
                <span class="pagination-info">${state.total} result${state.total !== 1 ? 's' : ''}</span>
            </div>`;
            return;
        }

        const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
        const currentPage = Math.floor(state.offset / state.limit) + 1;

        container.innerHTML = `<div class="pagination">
            <button class="pagination-btn" id="prev-page" ${currentPage <= 1 ? 'disabled' : ''}>Previous</button>
            <span class="pagination-info">Page ${currentPage} of ${totalPages} (${state.total} total)</span>
            <button class="pagination-btn" id="next-page" ${currentPage >= totalPages ? 'disabled' : ''}>Next</button>
        </div>`;
    }


    // --- Page Renderer ---
    App.registerPage('memories', async () => {
        // Reset state for fresh load
        state.expandedId = null;
        state.linkedCache = {};

        await loadMemories();

        return `
        <div class="page-header fade-in">
            <h1>Memories</h1>
            <p>Browse and search through Echo's stored memories</p>
        </div>

        <div class="search-bar-wrap fade-in">
            <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
            </svg>
            <input type="text" class="search-bar" id="memory-search"
                   placeholder="Search memories..."
                   value="${App.escapeHtml(state.searchQuery)}">
        </div>

        <div class="filter-row fade-in">
            <span class="filter-label">Type</span>
            <select class="filter-select" id="filter-type">
                <option value="">All Types</option>
                <option value="experience" ${state.memoryType === 'experience' ? 'selected' : ''}>Experience</option>
                <option value="fact" ${state.memoryType === 'fact' ? 'selected' : ''}>Fact</option>
                <option value="observation" ${state.memoryType === 'observation' ? 'selected' : ''}>Observation</option>
                <option value="reflection" ${state.memoryType === 'reflection' ? 'selected' : ''}>Reflection</option>
                <option value="insight" ${state.memoryType === 'insight' ? 'selected' : ''}>Insight</option>
                <option value="emotion" ${state.memoryType === 'emotion' ? 'selected' : ''}>Emotion</option>
            </select>

            <span class="filter-label">Sort</span>
            <select class="filter-select" id="filter-sort">
                <option value="created_at" ${state.sortBy === 'created_at' ? 'selected' : ''}>Date Created</option>
                <option value="importance" ${state.sortBy === 'importance' ? 'selected' : ''}>Importance</option>
                <option value="access_count" ${state.sortBy === 'access_count' ? 'selected' : ''}>Access Count</option>
                <option value="activation_level" ${state.sortBy === 'activation_level' ? 'selected' : ''}>Activation Level</option>
                <option value="emotional_weight" ${state.sortBy === 'emotional_weight' ? 'selected' : ''}>Emotional Weight</option>
                <option value="last_accessed" ${state.sortBy === 'last_accessed' ? 'selected' : ''}>Last Accessed</option>
            </select>

            <select class="filter-select" id="filter-order">
                <option value="desc" ${state.sortOrder === 'desc' ? 'selected' : ''}>Descending</option>
                <option value="asc" ${state.sortOrder === 'asc' ? 'selected' : ''}>Ascending</option>
            </select>
        </div>

        <div id="memory-list"></div>
        <div id="memory-pagination"></div>`;
    });


    // --- Post-render Initialization ---
    App.registerPage('memories_init', () => {
        renderList();

        let searchTimer = null;

        // Search input
        const searchEl = document.getElementById('memory-search');
        if (searchEl) {
            searchEl.addEventListener('input', () => {
                clearTimeout(searchTimer);
                searchTimer = setTimeout(async () => {
                    state.searchQuery = searchEl.value;
                    resetPagination();
                    await loadMemories();
                    renderList();
                }, 350);
            });

            // Clear search on Escape
            searchEl.addEventListener('keydown', async (e) => {
                if (e.key === 'Escape') {
                    searchEl.value = '';
                    state.searchQuery = '';
                    resetPagination();
                    await loadMemories();
                    renderList();
                }
            });
        }

        // Type filter
        const typeEl = document.getElementById('filter-type');
        if (typeEl) {
            typeEl.addEventListener('change', async () => {
                state.memoryType = typeEl.value;
                resetPagination();
                await loadMemories();
                renderList();
            });
        }

        // Sort filter
        const sortEl = document.getElementById('filter-sort');
        if (sortEl) {
            sortEl.addEventListener('change', async () => {
                state.sortBy = sortEl.value;
                resetPagination();
                await loadMemories();
                renderList();
            });
        }

        // Sort order
        const orderEl = document.getElementById('filter-order');
        if (orderEl) {
            orderEl.addEventListener('change', async () => {
                state.sortOrder = orderEl.value;
                resetPagination();
                await loadMemories();
                renderList();
            });
        }

        // Delegate clicks on the memory list
        const listEl = document.getElementById('memory-list');
        if (listEl) {
            listEl.addEventListener('click', async (e) => {
                // Expand / collapse
                const expandBtn = e.target.closest('.expand-btn');
                if (expandBtn) {
                    const id = parseInt(expandBtn.getAttribute('data-expand'), 10);
                    if (state.expandedId === id) {
                        state.expandedId = null;
                    } else {
                        state.expandedId = id;
                    }
                    renderList();

                    // Load linked memories if expanded
                    if (state.expandedId === id) {
                        const linked = await loadLinked(id);
                        const linkedEl = document.getElementById(`linked-${id}`);
                        if (linkedEl) {
                            if (linked.length === 0) {
                                linkedEl.innerHTML = '<p class="muted text-sm">No linked memories.</p>';
                            } else {
                                linkedEl.innerHTML = linked.map(lm =>
                                    `<div class="linked-memory">
                                        <div class="flex items-center gap-sm mb-2">
                                            ${App.typeBadge(lm.memory_type)}
                                            ${App.importanceBar(lm.importance)}
                                            ${lm.link_type ? `<span class="muted text-xs mono">${App.escapeHtml(lm.link_type)}</span>` : ''}
                                        </div>
                                        <div class="text-sm">${App.escapeHtml(App.truncateText(lm.content, 200))}</div>
                                    </div>`
                                ).join('');
                            }
                        }
                    }
                    return;
                }
            });
        }

        // Pagination clicks (delegated)
        const paginationEl = document.getElementById('memory-pagination');
        if (paginationEl) {
            paginationEl.addEventListener('click', async (e) => {
                if (e.target.id === 'prev-page' && state.offset >= state.limit) {
                    state.offset -= state.limit;
                    state.expandedId = null;
                    await loadMemories();
                    renderList();
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                } else if (e.target.id === 'next-page' && state.offset + state.limit < state.total) {
                    state.offset += state.limit;
                    state.expandedId = null;
                    await loadMemories();
                    renderList();
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                }
            });
        }
    });

})();
