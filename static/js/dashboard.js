/* ============================================================
   Megregore — Dashboard Page
   ============================================================ */

App.registerPage('dashboard', async () => {
    const stats = await App.api('/stats');

    const totalMemories = stats.total_memories || 0;
    const totalReflections = stats.total_reflections || 0;
    const avgImportance = stats.avg_importance || 0;
    const totalLinks = stats.total_links || 0;
    const totalSessions = stats.total_sessions || 0;
    const totalConsolidations = stats.total_consolidations || 0;
    const byType = stats.by_type || {};
    const recentMemories = stats.recent_memories || [];
    const strongestMemories = stats.strongest_memories || [];

    // Build type chart
    const maxTypeCount = Math.max(1, ...Object.values(byType));
    const typeOrder = ['experience', 'fact', 'observation', 'reflection', 'insight', 'emotion'];
    const typeBarRows = typeOrder
        .filter(t => byType[t])
        .map(t => {
            const count = byType[t];
            const pct = Math.round((count / maxTypeCount) * 100);
            return `<div class="bar-row">
                <span class="bar-label">${App.escapeHtml(t)}</span>
                <span class="bar-track"><span class="bar-fill ${t}" style="width:${pct}%"></span></span>
                <span class="bar-count">${count}</span>
            </div>`;
        }).join('');

    // Build recent memories list
    const recentHtml = recentMemories.length
        ? recentMemories.map(m => memoryCompactCard(m)).join('')
        : `<div class="empty-state" style="padding:30px 10px;">
            <p class="muted text-sm">No memories yet. They will appear here as Echo forms them.</p>
           </div>`;

    // Build strongest memories list
    const strongestHtml = strongestMemories.length
        ? strongestMemories.map(m => memoryCompactCard(m)).join('')
        : `<div class="empty-state" style="padding:30px 10px;">
            <p class="muted text-sm">No strong memories formed yet.</p>
           </div>`;

    // Identity snapshot
    let identitySnap = '';
    try {
        const identity = await App.api('/identity');
        const content = identity.content || '';
        if (content) {
            const preview = content.substring(0, 500);
            identitySnap = `<div class="identity-snapshot">${App.escapeHtml(preview)}</div>`;
        } else {
            identitySnap = `<div class="empty-state" style="padding:20px 10px;">
                <p class="muted text-sm">No identity document yet.</p>
            </div>`;
        }
    } catch (e) {
        identitySnap = `<div class="empty-state" style="padding:20px 10px;">
            <p class="muted text-sm">Could not load identity.</p>
        </div>`;
    }

    return `
    <div class="page-header fade-in">
        <h1>Dashboard</h1>
        <p>A high-level view of Echo's memory landscape</p>
    </div>

    <div class="stats-row">
        <div class="stat-card accent fade-in fade-in-delay-1">
            <div class="stat-label">Total Memories</div>
            <div class="stat-value">${totalMemories}</div>
        </div>
        <div class="stat-card fade-in fade-in-delay-2">
            <div class="stat-label">Reflections</div>
            <div class="stat-value">${totalReflections}</div>
        </div>
        <div class="stat-card teal fade-in fade-in-delay-3">
            <div class="stat-label">Avg Importance</div>
            <div class="stat-value">${avgImportance.toFixed(1)}</div>
            <div class="stat-sub">out of 10</div>
        </div>
        <div class="stat-card fade-in fade-in-delay-4">
            <div class="stat-label">Memory Links</div>
            <div class="stat-value">${totalLinks}</div>
        </div>
        <div class="stat-card fade-in fade-in-delay-1">
            <div class="stat-label">Sessions</div>
            <div class="stat-value">${totalSessions}</div>
        </div>
        <div class="stat-card fade-in fade-in-delay-2">
            <div class="stat-label">Consolidations</div>
            <div class="stat-value">${totalConsolidations}</div>
        </div>
    </div>

    <div class="section fade-in">
        <div class="section-title">Emotional Arc</div>
        <div class="chart-container">
            <canvas id="emotion-chart"></canvas>
        </div>
    </div>

    <div class="two-col">
        <div>
            <div class="section fade-in">
                <div class="section-title">
                    Recent Memories
                    <span class="count">${recentMemories.length}</span>
                </div>
                ${recentHtml}
            </div>

            <div class="section fade-in">
                <div class="section-title">Identity Snapshot</div>
                ${identitySnap}
            </div>
        </div>

        <div>
            <div class="section fade-in">
                <div class="section-title">
                    Strongest Memories
                    <span class="count">top ${strongestMemories.length}</span>
                </div>
                ${strongestHtml}
            </div>

            <div class="section fade-in">
                <div class="section-title">Memory Types</div>
                ${totalMemories > 0
                    ? `<div class="card"><div class="bar-chart">${typeBarRows}</div></div>`
                    : `<div class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">No type data yet.</p>
                       </div>`
                }
            </div>
        </div>
    </div>`;
});


// --- Dashboard Init (Emotional Timeline Chart) ---
App.registerPage('dashboard_init', () => {
    const canvas = document.getElementById('emotion-chart');
    if (!canvas || typeof Chart === 'undefined') return;

    App.api('/emotions/timeline', { days: 30, bucket: 'day' }).then(data => {
        const timeline = data.timeline || [];

        if (!timeline.length) {
            canvas.parentElement.innerHTML = '<p class="muted text-sm" style="padding:20px;text-align:center;">No emotional data yet.</p>';
            return;
        }

        const labels = timeline.map(t => t.bucket);
        const avgData = timeline.map(t => t.avg_emotion);
        const minData = timeline.map(t => t.min_emotion);
        const maxData = timeline.map(t => t.max_emotion);
        const counts = timeline.map(t => t.count);

        new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Avg Emotion',
                        data: avgData,
                        borderColor: '#7c5bf5',
                        backgroundColor: 'rgba(124, 91, 245, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        borderWidth: 2,
                    },
                    {
                        label: 'Max',
                        data: maxData,
                        borderColor: 'rgba(52, 211, 153, 0.5)',
                        borderDash: [4, 4],
                        pointRadius: 0,
                        borderWidth: 1,
                        fill: false,
                    },
                    {
                        label: 'Min',
                        data: minData,
                        borderColor: 'rgba(248, 113, 113, 0.5)',
                        borderDash: [4, 4],
                        pointRadius: 0,
                        borderWidth: 1,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index',
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#8888a0',
                            font: { size: 11 },
                        },
                    },
                    tooltip: {
                        callbacks: {
                            afterBody: (items) => {
                                const idx = items[0]?.dataIndex;
                                if (idx !== undefined && counts[idx]) {
                                    return `Memories: ${counts[idx]}`;
                                }
                                return '';
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#55556a', font: { size: 10 } },
                        grid: { color: 'rgba(30, 30, 46, 0.6)' },
                    },
                    y: {
                        min: -1,
                        max: 1,
                        ticks: { color: '#55556a', font: { size: 10 } },
                        grid: { color: 'rgba(30, 30, 46, 0.6)' },
                    },
                },
            },
        });
    }).catch(err => {
        console.error('Emotion chart error:', err);
        canvas.parentElement.innerHTML = '<p class="muted text-sm" style="padding:20px;text-align:center;">Could not load emotional timeline.</p>';
    });
});


// --- Compact Memory Card (for dashboard lists) ---
function memoryCompactCard(m) {
    const content = App.truncateText(m.content, 150);
    return `<div class="card" style="padding:14px 18px;">
        <div class="card-header">
            ${App.typeBadge(m.memory_type)}
            ${App.importanceBar(m.importance)}
        </div>
        <div class="card-content text-sm">${App.escapeHtml(content)}</div>
        <div class="card-meta">
            ${m.tags && m.tags.length ? App.tagPills(m.tags) : ''}
            <span class="card-meta-item muted">${App.formatDate(m.created_at)}</span>
        </div>
    </div>`;
}
