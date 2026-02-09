/* ============================================================
   Megregore — Identity Viewer Page
   ============================================================ */

(() => {

    App.registerPage('identity', async () => {
        let identity, history;

        try {
            [identity, history] = await Promise.all([
                App.api('/identity'),
                App.api('/identity/history'),
            ]);
        } catch (e) {
            return App.emptyState(
                'Could not load identity',
                'The identity data could not be retrieved. Is the API server running?'
            );
        }

        const content = identity.content || '';
        const version = identity.version || 0;
        const updatedAt = identity.updated_at || '';
        const historyItems = (history.history || []);

        // Current identity document
        const identityHtml = content
            ? `<div class="identity-doc">${App.renderMarkdown(content)}</div>`
            : App.emptyState('No identity yet', 'Echo has not formed an identity document yet. It will evolve over time.');

        // Version history timeline
        let historyHtml = '';
        if (historyItems.length > 0) {
            const timelineItems = historyItems.map((item, i) =>
                `<div class="timeline-item">
                    <div class="timeline-date">${App.formatDateFull(item.updated_at)}</div>
                    <div class="card history-card" data-history-index="${i}">
                        <div class="history-summary">
                            <div class="flex items-center gap-sm">
                                <span class="version-badge">v${item.version}</span>
                                <span class="text-sm">${App.escapeHtml(item.updated_reason || 'No reason given')}</span>
                            </div>
                            <svg class="expand-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M6 9l6 6 6-6"/>
                            </svg>
                        </div>
                        <div class="history-content">
                            <div class="history-content-inner">${App.escapeHtml(item.content || '')}</div>
                        </div>
                    </div>
                </div>`
            ).join('');

            historyHtml = `
            <div class="section mt-4">
                <div class="section-title">
                    Version History
                    <span class="count">${historyItems.length} version${historyItems.length !== 1 ? 's' : ''}</span>
                </div>
                <div class="timeline">
                    ${timelineItems}
                </div>
            </div>`;
        }

        return `
        <div class="page-header fade-in">
            <h1>Identity</h1>
            <p>Echo's evolving sense of self</p>
        </div>

        <div class="identity-header fade-in">
            ${version > 0 ? `<span class="version-badge">v${version}</span>` : ''}
            ${updatedAt ? `<span class="muted text-sm">Last updated ${App.formatDate(updatedAt)}</span>` : ''}
        </div>

        <div class="fade-in">
            ${identityHtml}
        </div>

        ${historyHtml}`;
    });

    // --- Post-render: Toggle history cards ---
    App.registerPage('identity_init', () => {
        document.querySelectorAll('.history-card').forEach(card => {
            card.addEventListener('click', () => {
                card.classList.toggle('expanded');
            });
        });
    });

})();
