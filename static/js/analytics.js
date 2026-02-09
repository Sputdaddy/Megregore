(() => {
    async function render() {
        // Show loading state while fetching
        let html = App.loading();
        let analytics = null;
        let topAccessed = null;
        let orphans = null;

        // Fetch all analytics data in parallel
        try {
            [analytics, topAccessed, orphans] = await Promise.all([
                App.api('/analytics'),
                App.api('/analytics/top-accessed', { days: 30, limit: 20 }),
                App.api('/analytics/orphans', { min_age_days: 7, limit: 20 })
            ]);
        } catch (error) {
            return `<div class="fade-in"><div class="card"><div class="card-content" style="color: #e74c3c;">Failed to load analytics: ${App.escapeHtml(error.message)}</div></div></div>`;
        }

        // Build stats row
        const statsCards = [
            {
                label: 'Total Memories',
                value: analytics.total_memories,
                className: ''
            },
            {
                label: 'Total Accesses',
                value: analytics.total_accesses,
                className: 'accent'
            },
            {
                label: 'Avg Activation',
                value: (analytics.avg_activation * 100).toFixed(1) + '%',
                className: 'teal'
            },
            {
                label: 'Orphan Count',
                value: analytics.orphan_count,
                className: ''
            },
            {
                label: 'Threaded Count',
                value: analytics.threaded_count,
                className: ''
            },
            {
                label: 'Thread Coverage',
                value: (analytics.thread_coverage_pct * 100).toFixed(1) + '%',
                className: 'accent'
            }
        ];

        let statsRowHtml = '<div class="stats-row">';
        statsCards.forEach(card => {
            statsRowHtml += `
                <div class="stat-card ${card.className}">
                    <div class="stat-label">${App.escapeHtml(card.label)}</div>
                    <div class="stat-value">${App.escapeHtml(card.value)}</div>
                </div>
            `;
        });
        statsRowHtml += '</div>';

        // Build top accessed section
        let topAccessedHtml = '<div class="card fade-in-delay-1">';
        topAccessedHtml += '<div class="card-header"><h3 class="section-title">Top Accessed</h3></div>';

        if (!topAccessed.memories || topAccessed.memories.length === 0) {
            topAccessedHtml += `<div class="card-content">${App.emptyState('No Accessed Memories', 'Memories will appear here as you use them')}</div>`;
        } else {
            topAccessedHtml += '<div class="card-content">';
            topAccessed.memories.forEach((mem, idx) => {
                const preview = App.truncateText(mem.content, 120);
                topAccessedHtml += `
                    <div class="memory-row" style="padding: 12px 0; border-bottom: 1px solid #ecf0f1; ${idx === topAccessed.memories.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <div style="flex: 1;">
                                <div style="font-size: 13px; color: #2c3e50; margin-bottom: 4px;">${App.escapeHtml(preview)}</div>
                                <div style="display: flex; gap: 12px; align-items: center;">
                                    <span style="font-size: 12px; color: #7f8c8d;">Accessed ${mem.recent_access_count} time${mem.recent_access_count !== 1 ? 's' : ''}</span>
                                    ${App.importanceBar(mem.importance)}
                                </div>
                            </div>
                        </div>
                        <div style="margin-top: 8px;">
                            <span style="font-size: 11px; color: #95a5a6; margin-right: 12px;">Activation</span>
                            ${App.activationBar(mem.activation_level)}
                        </div>
                    </div>
                `;
            });
            topAccessedHtml += '</div>';
        }
        topAccessedHtml += '</div>';

        // Build orphan memories section
        let orphansHtml = '<div class="card fade-in-delay-2">';
        orphansHtml += '<div class="card-header"><h3 class="section-title">Orphan Memories</h3></div>';

        if (!orphans.memories || orphans.memories.length === 0) {
            orphansHtml += `<div class="card-content">${App.emptyState('No Orphaned Memories', 'All your memories are linked or recently accessed')}</div>`;
        } else {
            orphansHtml += '<div class="card-content orphan-list">';
            orphans.memories.forEach((mem, idx) => {
                const preview = App.truncateText(mem.content, 120);
                const created = App.formatDate(mem.created_at);
                orphansHtml += `
                    <div style="padding: 12px 0; border-bottom: 1px solid #ecf0f1; ${idx === orphans.memories.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center;">
                            ${App.typeBadge(mem.memory_type)}
                            <span style="font-size: 12px; color: #7f8c8d;">${created}</span>
                        </div>
                        <div style="font-size: 13px; color: #2c3e50;">${App.escapeHtml(preview)}</div>
                        ${mem.tags && mem.tags.length > 0 ? `<div style="margin-top: 6px;">${App.tagPills(mem.tags)}</div>` : ''}
                    </div>
                `;
            });
            orphansHtml += '</div>';
        }
        orphansHtml += '</div>';

        // Build access by type chart
        let chartHtml = '<div class="card fade-in-delay-3">';
        chartHtml += '<div class="card-header"><h3 class="section-title">Access by Type</h3></div>';

        if (!analytics.access_by_type || Object.keys(analytics.access_by_type).length === 0) {
            chartHtml += `<div class="card-content">${App.emptyState('No Access Data', 'Access patterns will appear here')}</div>`;
        } else {
            chartHtml += '<div class="card-content">';
            chartHtml += '<div class="bar-chart">';

            // Find max count for scaling
            const counts = Object.values(analytics.access_by_type);
            const maxCount = Math.max(...counts);

            // Sort by count descending
            const sorted = Object.entries(analytics.access_by_type)
                .sort((a, b) => b[1] - a[1]);

            sorted.forEach(([type, count]) => {
                const pct = (count / maxCount) * 100;
                chartHtml += `
                    <div class="bar-row">
                        <div class="bar-label">${App.escapeHtml(type)}</div>
                        <div class="bar-track">
                            <div class="bar-fill" style="width: ${pct}%;"></div>
                        </div>
                        <div class="bar-count">${count}</div>
                    </div>
                `;
            });

            chartHtml += '</div>';
            chartHtml += '</div>';
        }
        chartHtml += '</div>';

        // Assemble full page
        html = `
            <div class="fade-in">
                <div class="page-header">
                    <h1>Analytics</h1>
                    <p>How your memories are being used</p>
                </div>

                ${statsRowHtml}

                <div class="analytics-grid">
                    <div class="analytics-card">
                        ${topAccessedHtml}
                    </div>
                    <div class="analytics-card">
                        ${orphansHtml}
                    </div>
                </div>

                <div style="margin-top: 20px;">
                    ${chartHtml}
                </div>
            </div>
        `;

        return html;
    }

    App.registerPage('analytics', render);
})();
