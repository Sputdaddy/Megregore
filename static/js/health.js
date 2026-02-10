(() => {
    async function render() {
        // Show loading state while fetching
        let html = App.loading();
        let healthReport = null;
        let consolidationCandidates = null;
        let suggestedLinks = null;

        // Fetch all health data in parallel
        try {
            [healthReport, consolidationCandidates, suggestedLinks] = await Promise.all([
                App.api('/health'),
                App.api('/health/consolidation-candidates'),
                App.api('/health/suggested-links')
            ]);
        } catch (error) {
            return `<div class="fade-in"><div class="card"><div class="card-content" style="color: #e74c3c;">Failed to load health data: ${App.escapeHtml(error.message)}</div></div></div>`;
        }

        // Helper for issue count color coding
        function issueColor(count) {
            if (count === 0) return '#27ae60';
            if (count <= 2) return '#f39c12';
            return '#e74c3c';
        }

        // Build summary stats row
        const summary = healthReport.summary || {};
        const statsCards = [
            {
                label: 'Total Issues',
                value: summary.total_issues || 0,
                color: issueColor(summary.total_issues || 0)
            },
            {
                label: 'Near Duplicates',
                value: summary.near_duplicates || 0,
                color: issueColor(summary.near_duplicates || 0)
            },
            {
                label: 'Anomalies',
                value: summary.anomalies || 0,
                color: issueColor(summary.anomalies || 0)
            },
            {
                label: 'Orphans',
                value: summary.orphans || 0,
                color: issueColor(summary.orphans || 0)
            },
            {
                label: 'Stale Threads',
                value: summary.stale_threads || 0,
                color: issueColor(summary.stale_threads || 0)
            }
        ];

        let statsRowHtml = '<div class="stats-row">';
        statsCards.forEach(card => {
            statsRowHtml += `
                <div class="stat-card" style="border-left: 4px solid ${card.color};">
                    <div class="stat-label">${App.escapeHtml(card.label)}</div>
                    <div class="stat-value" style="color: ${card.color};">${card.value}</div>
                </div>
            `;
        });
        statsRowHtml += '</div>';

        // Build near duplicates section
        let duplicatesHtml = '<div class="card fade-in-delay-1">';
        duplicatesHtml += '<div class="card-header"><h3 class="section-title">Near Duplicates</h3></div>';

        if (!healthReport.near_duplicates || healthReport.near_duplicates.length === 0) {
            duplicatesHtml += `<div class="card-content">${App.emptyState('No Duplicates Found', 'Your memories are distinct')}</div>`;
        } else {
            duplicatesHtml += '<div class="card-content">';
            healthReport.near_duplicates.forEach((dup, idx) => {
                const similarityPct = (dup.similarity * 100).toFixed(1);
                duplicatesHtml += `
                    <div style="padding: 16px 0; border-bottom: 1px solid #ecf0f1; ${idx === healthReport.near_duplicates.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span style="font-size: 12px; font-weight: 600; color: #e74c3c;">Similarity: ${similarityPct}%</span>
                            <span style="font-size: 11px; color: #95a5a6;">IDs: ${dup.memory_a_id}, ${dup.memory_b_id}</span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                            <div style="padding: 12px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid #3498db;">
                                <div style="font-size: 11px; color: #7f8c8d; margin-bottom: 6px; font-weight: 600;">Memory A</div>
                                <div style="font-size: 13px; color: #2c3e50;">${App.escapeHtml(App.truncateText(dup.content_a, 150))}</div>
                            </div>
                            <div style="padding: 12px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid #9b59b6;">
                                <div style="font-size: 11px; color: #7f8c8d; margin-bottom: 6px; font-weight: 600;">Memory B</div>
                                <div style="font-size: 13px; color: #2c3e50;">${App.escapeHtml(App.truncateText(dup.content_b, 150))}</div>
                            </div>
                        </div>
                    </div>
                `;
            });
            duplicatesHtml += '</div>';
        }
        duplicatesHtml += '</div>';

        // Build anomalies section
        let anomaliesHtml = '<div class="card fade-in-delay-2">';
        anomaliesHtml += '<div class="card-header"><h3 class="section-title">Anomalies</h3></div>';

        if (!healthReport.anomalies || healthReport.anomalies.length === 0) {
            anomaliesHtml += `<div class="card-content">${App.emptyState('No Anomalies Detected', 'Your memory patterns look healthy')}</div>`;
        } else {
            anomaliesHtml += '<div class="card-content">';
            healthReport.anomalies.forEach((anom, idx) => {
                const severityPct = (anom.severity * 100).toFixed(0);
                const severityColor = anom.severity > 0.7 ? '#e74c3c' : anom.severity > 0.4 ? '#f39c12' : '#27ae60';
                const anomalyBadgeColor = anom.anomaly_type === 'forgotten_important' ? '#e74c3c' : '#f39c12';
                const anomalyLabel = anom.anomaly_type === 'forgotten_important' ? 'Forgotten Important' : 'Undervalued';

                anomaliesHtml += `
                    <div style="padding: 14px 0; border-bottom: 1px solid #ecf0f1; ${idx === healthReport.anomalies.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center;">
                            <span style="display: inline-block; padding: 3px 8px; background: ${anomalyBadgeColor}; color: white; border-radius: 4px; font-size: 11px; font-weight: 600;">${anomalyLabel}</span>
                            <span style="font-size: 11px; color: #95a5a6;">ID: ${anom.memory_id}</span>
                        </div>
                        <div style="font-size: 13px; color: #2c3e50; margin-bottom: 10px;">${App.escapeHtml(App.truncateText(anom.content, 120))}</div>
                        <div style="display: flex; gap: 16px; align-items: center; font-size: 11px; color: #7f8c8d;">
                            <span>Importance: ${anom.importance}/10</span>
                            <span>Activation: ${(anom.activation_level * 100).toFixed(1)}%</span>
                        </div>
                        <div style="margin-top: 8px;">
                            <div style="font-size: 11px; color: #7f8c8d; margin-bottom: 4px;">Severity: ${severityPct}%</div>
                            <div style="width: 100%; height: 6px; background: #ecf0f1; border-radius: 3px; overflow: hidden;">
                                <div style="height: 100%; width: ${severityPct}%; background: linear-gradient(to right, #27ae60, #f39c12, #e74c3c); background-size: 300% 100%; background-position: ${severityPct}% 0;"></div>
                            </div>
                        </div>
                    </div>
                `;
            });
            anomaliesHtml += '</div>';
        }
        anomaliesHtml += '</div>';

        // Build orphans section
        let orphansHtml = '<div class="card fade-in-delay-3">';
        orphansHtml += '<div class="card-header"><h3 class="section-title">Orphaned Memories</h3></div>';

        if (!healthReport.orphans || healthReport.orphans.length === 0) {
            orphansHtml += `<div class="card-content">${App.emptyState('No Orphans', 'All memories are linked or recently accessed')}</div>`;
        } else {
            orphansHtml += '<div class="card-content">';
            healthReport.orphans.forEach((orphan, idx) => {
                const preview = App.truncateText(orphan.content, 120);
                const created = App.formatDate(orphan.created_at);
                orphansHtml += `
                    <div style="padding: 12px 0; border-bottom: 1px solid #ecf0f1; ${idx === healthReport.orphans.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center; flex-wrap: wrap;">
                            ${App.typeBadge(orphan.memory_type)}
                            <span style="font-size: 12px; color: #7f8c8d;">${created}</span>
                            <span style="font-size: 11px; color: #95a5a6;">${orphan.days_old} days old</span>
                            ${App.importanceBar(orphan.importance)}
                        </div>
                        <div style="font-size: 13px; color: #2c3e50; margin-bottom: 6px;">${App.escapeHtml(preview)}</div>
                        ${orphan.tags && orphan.tags.length > 0 ? `<div style="margin-top: 6px;">${App.tagPills(orphan.tags)}</div>` : ''}
                    </div>
                `;
            });
            orphansHtml += '</div>';
        }
        orphansHtml += '</div>';

        // Build stale threads section
        let staleThreadsHtml = '<div class="card fade-in-delay-4">';
        staleThreadsHtml += '<div class="card-header"><h3 class="section-title">Stale Threads</h3></div>';

        if (!healthReport.stale_threads || healthReport.stale_threads.length === 0) {
            staleThreadsHtml += `<div class="card-content">${App.emptyState('No Stale Threads', 'All threads are active or archived')}</div>`;
        } else {
            staleThreadsHtml += '<div class="card-content">';
            healthReport.stale_threads.forEach((thread, idx) => {
                const lastActive = App.formatDate(thread.last_active);
                const created = App.formatDate(thread.created_at);
                staleThreadsHtml += `
                    <div style="padding: 12px 0; border-bottom: 1px solid #ecf0f1; ${idx === healthReport.stale_threads.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                            <div style="font-size: 14px; font-weight: 600; color: #2c3e50;">${App.escapeHtml(thread.title || 'Untitled Thread')}</div>
                            <span style="font-size: 11px; color: #95a5a6;">ID: ${thread.thread_id}</span>
                        </div>
                        <div style="display: flex; gap: 16px; font-size: 12px; color: #7f8c8d;">
                            <span>Memories: ${thread.memory_count}</span>
                            <span>Created: ${created}</span>
                            <span>Last Active: ${lastActive}</span>
                        </div>
                    </div>
                `;
            });
            staleThreadsHtml += '</div>';
        }
        staleThreadsHtml += '</div>';

        // Build consolidation candidates section
        let consolidationHtml = '<div class="card fade-in-delay-5">';
        consolidationHtml += '<div class="card-header"><h3 class="section-title">Consolidation Candidates</h3></div>';

        if (!consolidationCandidates.candidates || consolidationCandidates.candidates.length === 0) {
            consolidationHtml += `<div class="card-content">${App.emptyState('No Consolidation Candidates', 'No memory groups found for consolidation')}</div>`;
        } else {
            consolidationHtml += '<div class="card-content">';
            consolidationCandidates.candidates.forEach((candidate, idx) => {
                const confidencePct = (candidate.confidence * 100).toFixed(0);
                const confidenceColor = candidate.confidence > 0.8 ? '#27ae60' : candidate.confidence > 0.6 ? '#f39c12' : '#e74c3c';
                consolidationHtml += `
                    <div style="padding: 16px 0; border-bottom: 1px solid #ecf0f1; ${idx === consolidationCandidates.candidates.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div>
                                <span style="font-size: 12px; font-weight: 600; color: #2c3e50;">${App.escapeHtml(candidate.reason)}</span>
                                <span style="margin-left: 8px; font-size: 11px; color: #95a5a6;">${candidate.memory_ids.length} memories</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 11px; color: #7f8c8d;">Confidence:</span>
                                <span style="font-size: 12px; font-weight: 600; color: ${confidenceColor};">${confidencePct}%</span>
                            </div>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 8px;">
                            ${candidate.previews.map(preview => `
                                <div style="padding: 10px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid #3498db;">
                                    <div style="font-size: 11px; color: #7f8c8d; margin-bottom: 4px;">ID: ${preview.id}</div>
                                    <div style="font-size: 13px; color: #2c3e50;">${App.escapeHtml(App.truncateText(preview.content, 100))}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            });
            consolidationHtml += '</div>';
        }
        consolidationHtml += '</div>';

        // Build suggested links section
        let suggestedLinksHtml = '<div class="card fade-in-delay-6">';
        suggestedLinksHtml += '<div class="card-header"><h3 class="section-title">Suggested Links</h3></div>';

        if (!suggestedLinks.suggestions || suggestedLinks.suggestions.length === 0) {
            suggestedLinksHtml += `<div class="card-content">${App.emptyState('No Link Suggestions', 'No potential connections found')}</div>`;
        } else {
            suggestedLinksHtml += '<div class="card-content">';
            suggestedLinks.suggestions.forEach((suggestion, idx) => {
                const similarityPct = (suggestion.similarity * 100).toFixed(1);
                suggestedLinksHtml += `
                    <div style="padding: 16px 0; border-bottom: 1px solid #ecf0f1; ${idx === suggestedLinks.suggestions.length - 1 ? 'border-bottom: none;' : ''}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span style="font-size: 12px; font-weight: 600; color: #27ae60;">Similarity: ${similarityPct}%</span>
                            <span style="font-size: 11px; color: #95a5a6;">IDs: ${suggestion.source_id} → ${suggestion.target_id}</span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                            <div style="padding: 12px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid #3498db;">
                                <div style="font-size: 11px; color: #7f8c8d; margin-bottom: 6px; font-weight: 600;">Source</div>
                                <div style="font-size: 13px; color: #2c3e50;">${App.escapeHtml(App.truncateText(suggestion.source_content, 120))}</div>
                            </div>
                            <div style="padding: 12px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid #9b59b6;">
                                <div style="font-size: 11px; color: #7f8c8d; margin-bottom: 6px; font-weight: 600;">Target</div>
                                <div style="font-size: 13px; color: #2c3e50;">${App.escapeHtml(App.truncateText(suggestion.target_content, 120))}</div>
                            </div>
                        </div>
                    </div>
                `;
            });
            suggestedLinksHtml += '</div>';
        }
        suggestedLinksHtml += '</div>';

        // Assemble full page
        html = `
            <div class="fade-in">
                <div class="page-header">
                    <h1>Health</h1>
                    <p>Memory system diagnostics and recommendations</p>
                </div>

                ${statsRowHtml}

                <div style="margin-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        ${duplicatesHtml}
                    </div>
                    <div>
                        ${anomaliesHtml}
                    </div>
                </div>

                <div style="margin-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        ${orphansHtml}
                    </div>
                    <div>
                        ${staleThreadsHtml}
                    </div>
                </div>

                <div style="margin-top: 20px;">
                    ${consolidationHtml}
                </div>

                <div style="margin-top: 20px;">
                    ${suggestedLinksHtml}
                </div>
            </div>
        `;

        return html;
    }

    App.registerPage('health', render);
})();
