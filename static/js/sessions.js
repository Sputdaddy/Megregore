/* ============================================================
   Megregore — Sessions Page
   ============================================================ */

App.registerPage('sessions', async () => {
    const data = await App.api('/sessions', { limit: 50 });
    const sessions = data.sessions || [];

    if (!sessions.length) {
        return `
        <div class="page-header fade-in">
            <h1>Sessions</h1>
            <p>Conversation sessions with Echo</p>
        </div>
        ${App.emptyState('No sessions yet', 'Sessions are created when Echo forms memories during conversations.')}`;
    }

    const sessionCards = sessions.map(s => {
        const memCount = s.memory_count || 0;
        return `<div class="session-card fade-in" data-session-id="${App.escapeHtml(s.id)}" onclick="toggleSession(this)">
            <div class="session-header">
                <div>
                    <span class="session-id">${App.escapeHtml(s.id)}</span>
                    <span class="mood-dot neutral" id="mood-${App.escapeHtml(s.id)}"></span>
                </div>
                <div class="session-stats">
                    <span class="stat"><span class="stat-num">${memCount}</span> memories</span>
                    <span class="stat">${App.formatDate(s.started_at)}</span>
                </div>
            </div>
            ${s.summary ? `<div class="text-sm muted" style="margin-bottom:8px;">${App.escapeHtml(s.summary)}</div>` : ''}
            <div class="card-meta">
                <span class="card-meta-item muted">Started ${App.formatDateFull(s.started_at)}</span>
                <span class="card-meta-item muted">Last active ${App.formatDate(s.last_active)}</span>
            </div>
            <div class="session-memories">
                <div class="session-memories-inner" id="memories-${App.escapeHtml(s.id)}">
                    ${App.loading()}
                </div>
            </div>
        </div>`;
    }).join('');

    return `
    <div class="page-header fade-in">
        <h1>Sessions</h1>
        <p>${sessions.length} conversation session${sessions.length !== 1 ? 's' : ''} recorded</p>
    </div>
    ${sessionCards}`;
});


async function toggleSession(el) {
    const isExpanded = el.classList.contains('expanded');

    // Collapse all
    document.querySelectorAll('.session-card.expanded').forEach(card => {
        card.classList.remove('expanded');
    });

    if (isExpanded) return;

    el.classList.add('expanded');

    const sessionId = el.getAttribute('data-session-id');
    const container = document.getElementById('memories-' + sessionId);
    const moodDot = document.getElementById('mood-' + sessionId);

    try {
        // Fetch mood and memories in parallel
        const [moodData, memData] = await Promise.all([
            App.api('/sessions/' + sessionId),
            App.api('/sessions/' + sessionId + '/memories', { limit: 20 }),
        ]);

        // Update mood dot
        const mood = moodData.mood || {};
        const avg = mood.avg_emotion || 0;
        moodDot.className = 'mood-dot ' + (avg > 0.05 ? 'positive' : avg < -0.05 ? 'negative' : 'neutral');
        moodDot.title = 'Avg emotion: ' + avg.toFixed(3);

        const memories = memData.memories || [];
        if (!memories.length) {
            container.innerHTML = '<p class="muted text-sm" style="padding:8px 0;">No memories in this session.</p>';
            return;
        }

        container.innerHTML = memories.map(m => {
            const content = App.truncateText(m.content, 200);
            return `<div class="card" style="padding:12px 16px;">
                <div class="card-header">
                    ${App.typeBadge(m.memory_type)}
                    ${App.importanceBar(m.importance)}
                    ${App.emotionalIndicator(m.emotional_weight)}
                </div>
                <div class="card-content text-sm">${App.escapeHtml(content)}</div>
                <div class="card-meta">
                    ${m.tags && m.tags.length ? App.tagPills(m.tags) : ''}
                    <span class="card-meta-item muted">${App.formatDate(m.created_at)}</span>
                </div>
            </div>`;
        }).join('');
    } catch (err) {
        container.innerHTML = '<p class="muted text-sm">Failed to load session data.</p>';
        console.error('Session load error:', err);
    }
}
