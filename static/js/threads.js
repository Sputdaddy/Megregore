/* ============================================================
   Megregore — Threads Page
   ============================================================ */

App.registerPage('threads', async () => {
    const data = await App.api('/threads', { limit: 50 });
    const threads = data.threads || [];

    if (!threads.length) {
        return `
        <div class="page-header fade-in">
            <h1>Threads</h1>
            <p>Semantic topic groupings across sessions</p>
        </div>
        ${App.emptyState('No threads yet', 'Threads are semantic groupings of related memories that span across sessions.')}`;
    }

    const threadCards = threads.map(t => {
        const memCount = t.memory_count || 0;
        return `<div class="thread-card fade-in" data-thread-id="${App.escapeHtml(t.id)}">
            <div class="thread-title">${App.escapeHtml(t.title)}</div>
            ${t.description ? `<div class="thread-description">${App.escapeHtml(t.description)}</div>` : ''}
            <div class="thread-meta">
                <span class="card-meta-item"><span class="stat-num">${memCount}</span> memories</span>
                <span class="card-meta-item muted">Last active ${App.formatDate(t.last_active)}</span>
                <span class="card-meta-item muted">Created ${App.formatDate(t.created_at)}</span>
            </div>
            <div class="thread-detail" style="display: none;">
            </div>
        </div>`;
    }).join('');

    return `
    <div class="page-header fade-in">
        <h1>Threads</h1>
        <p>${threads.length} semantic thread${threads.length !== 1 ? 's' : ''}</p>
    </div>
    ${threadCards}`;
});


function initThreadListeners() {
    document.querySelectorAll('.thread-card').forEach(card => {
        card.addEventListener('click', async () => {
            const isExpanded = card.classList.contains('expanded');

            // Collapse all other threads
            document.querySelectorAll('.thread-card.expanded').forEach(c => {
                if (c !== card) {
                    c.classList.remove('expanded');
                }
            });

            // Toggle this one
            card.classList.toggle('expanded');
            const detail = card.querySelector('.thread-detail');

            if (card.classList.contains('expanded') && !detail.dataset.loaded) {
                detail.dataset.loaded = 'true';
                detail.innerHTML = App.loading();

                const threadId = card.getAttribute('data-thread-id');

                try {
                    const data = await App.api(`/threads/${threadId}/memories`, { limit: 100 });
                    const memories = data.memories || [];

                    if (!memories.length) {
                        detail.innerHTML = '<p class="muted text-sm" style="padding: 12px 0;">No memories in this thread.</p>';
                        return;
                    }

                    detail.innerHTML = renderThreadMemories(memories);
                } catch (err) {
                    detail.innerHTML = '<p class="muted text-sm">Failed to load thread memories.</p>';
                    console.error('Thread load error:', err);
                }
            }
        });
    });
}


function renderThreadMemories(memories) {
    return memories.map(m => {
        const content = App.truncateText(m.content, 250);
        return `<div class="card" style="padding: 14px 18px; margin-bottom: 8px;">
            <div class="card-header">
                ${App.typeBadge(m.memory_type)}
                ${App.importanceBar(m.importance)}
                ${App.activationBar(m.activation_level || 0)}
            </div>
            <div class="card-content text-sm">${App.escapeHtml(content)}</div>
            <div class="card-meta">
                ${m.tags && m.tags.length ? App.tagPills(m.tags) : ''}
                <span class="card-meta-item muted">${App.formatDate(m.created_at)}</span>
            </div>
        </div>`;
    }).join('');
}


App.registerPage('threads_init', initThreadListeners);
