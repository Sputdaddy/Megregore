/* ============================================================
   Megregore — Reflections Page
   ============================================================ */

(() => {

    let state = {
        reflections: [],
        total: 0,
        offset: 0,
        limit: 30,
        insightType: '',
    };

    async function loadReflections() {
        const data = await App.api('/reflections', {
            limit: state.limit,
            offset: state.offset,
            insight_type: state.insightType || null,
        });
        state.reflections = data.reflections || [];
        state.total = data.total || 0;
    }


    function renderReflectionCard(r) {
        const memoryIds = r.memory_ids || [];
        const memoryIdStr = memoryIds.length
            ? `<span class="card-meta-item muted mono text-xs">memories: ${memoryIds.join(', ')}</span>`
            : '';

        return `<div class="timeline-item">
            <div class="timeline-date">${App.formatDateFull(r.created_at)}</div>
            <div class="card">
                <div class="card-header">
                    ${App.insightBadge(r.insight_type)}
                </div>
                <div class="card-content">${App.escapeHtml(r.content)}</div>
                <div class="card-meta">
                    ${memoryIdStr}
                    ${r.session_id ? `<span class="card-meta-item muted mono text-xs">session: ${App.escapeHtml(r.session_id)}</span>` : ''}
                    <span class="card-meta-item muted">${App.formatDate(r.created_at)}</span>
                </div>
            </div>
        </div>`;
    }

    function renderList() {
        const container = document.getElementById('reflections-list');
        if (!container) return;

        if (state.reflections.length === 0) {
            container.innerHTML = App.emptyState(
                'No reflections yet',
                'Reflections appear when Echo synthesizes memories into insights. They represent patterns, growth, connections, and realizations formed through experience.'
            );
        } else {
            container.innerHTML = `<div class="timeline">
                ${state.reflections.map(r => renderReflectionCard(r)).join('')}
            </div>`;
        }

        renderPagination();
    }

    function renderPagination() {
        const container = document.getElementById('reflections-pagination');
        if (!container) return;

        if (state.total <= state.limit) {
            container.innerHTML = state.total > 0
                ? `<div class="pagination"><span class="pagination-info">${state.total} reflection${state.total !== 1 ? 's' : ''}</span></div>`
                : '';
            return;
        }

        const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
        const currentPage = Math.floor(state.offset / state.limit) + 1;

        container.innerHTML = `<div class="pagination">
            <button class="pagination-btn" id="ref-prev" ${currentPage <= 1 ? 'disabled' : ''}>Previous</button>
            <span class="pagination-info">Page ${currentPage} of ${totalPages} (${state.total} total)</span>
            <button class="pagination-btn" id="ref-next" ${currentPage >= totalPages ? 'disabled' : ''}>Next</button>
        </div>`;
    }


    // --- Page Renderer ---
    App.registerPage('reflections', async () => {
        state.offset = 0;
        await loadReflections();

        const insightTypes = ['pattern', 'growth', 'connection', 'realization'];

        const chips = insightTypes.map(t =>
            `<button class="filter-chip ${state.insightType === t ? 'active' : ''}" data-insight="${t}">${t}</button>`
        ).join('');

        return `
        <div class="page-header fade-in">
            <h1>Reflections</h1>
            <p>Echo's synthesis of memories into understanding</p>
        </div>

        <div class="filter-chips fade-in">
            <button class="filter-chip ${state.insightType === '' ? 'active' : ''}" data-insight="">All</button>
            ${chips}
        </div>

        <div id="reflections-list" class="fade-in"></div>
        <div id="reflections-pagination"></div>`;
    });


    // --- Post-render Initialization ---
    App.registerPage('reflections_init', () => {
        renderList();

        // Filter chips
        document.querySelectorAll('.filter-chip[data-insight]').forEach(chip => {
            chip.addEventListener('click', async () => {
                state.insightType = chip.getAttribute('data-insight');
                state.offset = 0;

                // Update active state
                document.querySelectorAll('.filter-chip[data-insight]').forEach(c =>
                    c.classList.toggle('active', c.getAttribute('data-insight') === state.insightType)
                );

                await loadReflections();
                renderList();
            });
        });

        // Pagination
        const pagEl = document.getElementById('reflections-pagination');
        if (pagEl) {
            pagEl.addEventListener('click', async (e) => {
                if (e.target.id === 'ref-prev' && state.offset >= state.limit) {
                    state.offset -= state.limit;
                    await loadReflections();
                    renderList();
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                } else if (e.target.id === 'ref-next' && state.offset + state.limit < state.total) {
                    state.offset += state.limit;
                    await loadReflections();
                    renderList();
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                }
            });
        }
    });

})();
