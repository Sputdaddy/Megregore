/* ============================================================
   Megregore — Health Page (Vue Component)
   ============================================================ */

megregoreApp.component('health-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const healthReport = ref({});
        const consolidationCandidates = ref([]);
        const suggestedLinks = ref([]);

        // --- Helper functions (exposed to template) ---

        function issueColor(count) {
            if (count === 0) return '#27ae60';
            if (count <= 2) return '#f39c12';
            return '#e74c3c';
        }

        function candidenceColor(confidence) {
            if (confidence > 0.8) return '#27ae60';
            if (confidence > 0.6) return '#f39c12';
            return '#e74c3c';
        }

        function anomalyBadgeHtml(type) {
            const color = type === 'forgotten_important' ? '#e74c3c' : '#f39c12';
            const label = type === 'forgotten_important' ? 'Forgotten Important' : 'Undervalued';
            return '<span style="display: inline-block; padding: 3px 8px; background: '
                + color + '; color: white; border-radius: 4px; font-size: 11px; font-weight: 600;">'
                + label + '</span>';
        }

        const formatDate = App.formatDate;
        const truncate = App.truncateText;
        const typeBadgeHtml = App.typeBadge;
        const importanceBarHtml = App.importanceBar;
        const tagPillsHtml = App.tagPills;

        // --- Computed ---

        const statCards = computed(() => {
            const summary = healthReport.value.summary || {};
            return [
                {
                    label: 'Total Issues',
                    value: summary.total_issues || 0,
                    color: issueColor(summary.total_issues || 0),
                },
                {
                    label: 'Near Duplicates',
                    value: summary.near_duplicates || 0,
                    color: issueColor(summary.near_duplicates || 0),
                },
                {
                    label: 'Anomalies',
                    value: summary.anomalies || 0,
                    color: issueColor(summary.anomalies || 0),
                },
                {
                    label: 'Orphans',
                    value: summary.orphans || 0,
                    color: issueColor(summary.orphans || 0),
                },
                {
                    label: 'Stale Threads',
                    value: summary.stale_threads || 0,
                    color: issueColor(summary.stale_threads || 0),
                },
            ];
        });

        const nearDuplicates = computed(() => healthReport.value.near_duplicates || []);
        const anomalies = computed(() => healthReport.value.anomalies || []);
        const orphans = computed(() => healthReport.value.orphans || []);
        const staleThreads = computed(() => healthReport.value.stale_threads || []);

        // --- Data Loading ---

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                const [healthData, consolidationData, linksData] = await Promise.all([
                    App.api('/health'),
                    App.api('/health/consolidation-candidates'),
                    App.api('/health/suggested-links'),
                ]);

                healthReport.value = healthData;
                consolidationCandidates.value = consolidationData.candidates || [];
                suggestedLinks.value = linksData.suggestions || [];
            } catch (err) {
                console.error('Health page load error:', err);
                error.value = err.message;
            } finally {
                loading.value = false;
            }
        }

        onMounted(() => {
            loadData();
        });

        return {
            loading,
            error,
            statCards,
            nearDuplicates,
            anomalies,
            orphans,
            staleThreads,
            consolidationCandidates,
            suggestedLinks,
            // Helper functions
            formatDate,
            truncate,
            typeBadgeHtml,
            importanceBarHtml,
            tagPillsHtml,
            anomalyBadgeHtml,
            candidenceColor,
        };
    },

    template: `
        <div v-if="loading" class="loading"><div class="spinner"></div></div>

        <div v-else-if="error" class="empty-state fade-in">
            <h3>Something went wrong</h3>
            <p>{{ error }}</p>
        </div>

        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Health</h1>
                <p>Memory system diagnostics and recommendations</p>
            </div>

            <!-- Stat Cards with Color Coding -->
            <div class="stats-row">
                <div v-for="(card, i) in statCards" :key="card.label"
                     class="stat-card fade-in" :class="'fade-in-delay-' + (i % 4 + 1)"
                     :style="{ borderLeftColor: card.color, borderLeftStyle: 'solid', borderLeftWidth: '4px' }">
                    <div class="stat-label">{{ card.label }}</div>
                    <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
                </div>
            </div>

            <!-- Near Duplicates + Anomalies Grid -->
            <div class="two-col">
                <!-- Near Duplicates -->
                <div class="section fade-in">
                    <div class="section-title">
                        Near Duplicates
                        <span class="count">{{ nearDuplicates.length }}</span>
                    </div>
                    <template v-if="nearDuplicates.length">
                        <div v-for="(dup, idx) in nearDuplicates" :key="idx" class="card">
                            <div style="padding: 16px; border-bottom: 1px solid var(--border);" :style="{ borderBottom: idx === nearDuplicates.length - 1 ? 'none' : '' }">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                    <span style="font-size: 12px; font-weight: 600; color: #e74c3c;">Similarity: {{ (dup.similarity * 100).toFixed(1) }}%</span>
                                    <span style="font-size: 11px; color: var(--text-secondary);">IDs: {{ dup.memory_a_id }}, {{ dup.memory_b_id }}</span>
                                </div>
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                                    <div style="padding: 12px; background: var(--bg-surface); border-radius: 6px; border-left: 3px solid #3498db;">
                                        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600;">Memory A</div>
                                        <div style="font-size: 13px; color: var(--text-primary);">{{ truncate(dup.content_a, 150) }}</div>
                                    </div>
                                    <div style="padding: 12px; background: var(--bg-surface); border-radius: 6px; border-left: 3px solid #9b59b6;">
                                        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600;">Memory B</div>
                                        <div style="font-size: 13px; color: var(--text-primary);">{{ truncate(dup.content_b, 150) }}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </template>
                    <div v-else class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">No near duplicates found.</p>
                    </div>
                </div>

                <!-- Anomalies -->
                <div class="section fade-in">
                    <div class="section-title">
                        Anomalies
                        <span class="count">{{ anomalies.length }}</span>
                    </div>
                    <template v-if="anomalies.length">
                        <div v-for="(anom, idx) in anomalies" :key="idx" class="card">
                            <div style="padding: 14px 16px; border-bottom: 1px solid var(--border);" :style="{ borderBottom: idx === anomalies.length - 1 ? 'none' : '' }">
                                <div style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center;">
                                    <span v-html="anomalyBadgeHtml(anom.anomaly_type)"></span>
                                    <span style="font-size: 11px; color: var(--text-secondary);">ID: {{ anom.memory_id }}</span>
                                </div>
                                <div style="font-size: 13px; color: var(--text-primary); margin-bottom: 10px;">{{ truncate(anom.content, 120) }}</div>
                                <div style="display: flex; gap: 16px; align-items: center; font-size: 11px; color: var(--text-muted); margin-bottom: 10px;">
                                    <span>Importance: {{ anom.importance }}/10</span>
                                    <span>Activation: {{ (anom.activation_level * 100).toFixed(1) }}%</span>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Severity: {{ (anom.severity * 100).toFixed(0) }}%</div>
                                    <div style="width: 100%; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden;">
                                        <div :style="{ height: '100%', width: (anom.severity * 100).toFixed(0) + '%', background: 'linear-gradient(to right, #27ae60, #f39c12, #e74c3c)', backgroundSize: '300% 100%', backgroundPosition: (anom.severity * 100).toFixed(0) + '% 0' }"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </template>
                    <div v-else class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">No anomalies detected.</p>
                    </div>
                </div>
            </div>

            <!-- Orphans + Stale Threads Grid -->
            <div class="two-col">
                <!-- Orphaned Memories -->
                <div class="section fade-in">
                    <div class="section-title">
                        Orphaned Memories
                        <span class="count">{{ orphans.length }}</span>
                    </div>
                    <template v-if="orphans.length">
                        <div v-for="(orphan, idx) in orphans" :key="idx" class="card">
                            <div style="padding: 12px 16px; border-bottom: 1px solid var(--border);" :style="{ borderBottom: idx === orphans.length - 1 ? 'none' : '' }">
                                <div style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center; flex-wrap: wrap;">
                                    <span v-html="typeBadgeHtml(orphan.memory_type)"></span>
                                    <span style="font-size: 12px; color: var(--text-muted);">{{ formatDate(orphan.created_at) }}</span>
                                    <span style="font-size: 11px; color: var(--text-secondary);">{{ orphan.days_old }} days old</span>
                                    <span v-html="importanceBarHtml(orphan.importance)"></span>
                                </div>
                                <div style="font-size: 13px; color: var(--text-primary); margin-bottom: 6px;">{{ truncate(orphan.content, 120) }}</div>
                                <div v-if="orphan.tags && orphan.tags.length" style="margin-top: 6px;" v-html="tagPillsHtml(orphan.tags)"></div>
                            </div>
                        </div>
                    </template>
                    <div v-else class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">No orphaned memories.</p>
                    </div>
                </div>

                <!-- Stale Threads -->
                <div class="section fade-in">
                    <div class="section-title">
                        Stale Threads
                        <span class="count">{{ staleThreads.length }}</span>
                    </div>
                    <template v-if="staleThreads.length">
                        <div v-for="(thread, idx) in staleThreads" :key="thread.thread_id" class="card">
                            <div style="padding: 12px 16px; border-bottom: 1px solid var(--border);" :style="{ borderBottom: idx === staleThreads.length - 1 ? 'none' : '' }">
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                                    <div style="font-size: 14px; font-weight: 600; color: var(--text-primary);">{{ thread.title || 'Untitled Thread' }}</div>
                                    <span style="font-size: 11px; color: var(--text-secondary);">ID: {{ thread.thread_id }}</span>
                                </div>
                                <div style="display: flex; gap: 16px; font-size: 12px; color: var(--text-muted);">
                                    <span>Memories: {{ thread.memory_count }}</span>
                                    <span>Created: {{ formatDate(thread.created_at) }}</span>
                                    <span>Last Active: {{ formatDate(thread.last_active) }}</span>
                                </div>
                            </div>
                        </div>
                    </template>
                    <div v-else class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">No stale threads.</p>
                    </div>
                </div>
            </div>

            <!-- Consolidation Candidates -->
            <div class="section fade-in">
                <div class="section-title">
                    Consolidation Candidates
                    <span class="count">{{ consolidationCandidates.length }}</span>
                </div>
                <template v-if="consolidationCandidates.length">
                    <div v-for="(candidate, idx) in consolidationCandidates" :key="idx" class="card">
                        <div style="padding: 16px; border-bottom: 1px solid var(--border);" :style="{ borderBottom: idx === consolidationCandidates.length - 1 ? 'none' : '' }">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <div>
                                    <span style="font-size: 12px; font-weight: 600; color: var(--text-primary);">{{ candidate.reason }}</span>
                                    <span style="margin-left: 8px; font-size: 11px; color: var(--text-secondary);">{{ candidate.memory_ids.length }} memories</span>
                                </div>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 11px; color: var(--text-muted);">Confidence:</span>
                                    <span style="font-size: 12px; font-weight: 600;" :style="{ color: candidenceColor(candidate.confidence) }">{{ (candidate.confidence * 100).toFixed(0) }}%</span>
                                </div>
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 8px;">
                                <div v-for="preview in candidate.previews" :key="preview.id" style="padding: 10px; background: var(--bg-surface); border-radius: 6px; border-left: 3px solid #3498db;">
                                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">ID: {{ preview.id }}</div>
                                    <div style="font-size: 13px; color: var(--text-primary);">{{ truncate(preview.content, 100) }}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </template>
                <div v-else class="empty-state" style="padding:30px 10px;">
                    <p class="muted text-sm">No consolidation candidates found.</p>
                </div>
            </div>

            <!-- Suggested Links -->
            <div class="section fade-in">
                <div class="section-title">
                    Suggested Links
                    <span class="count">{{ suggestedLinks.length }}</span>
                </div>
                <template v-if="suggestedLinks.length">
                    <div v-for="(suggestion, idx) in suggestedLinks" :key="idx" class="card">
                        <div style="padding: 16px; border-bottom: 1px solid var(--border);" :style="{ borderBottom: idx === suggestedLinks.length - 1 ? 'none' : '' }">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <span style="font-size: 12px; font-weight: 600; color: #27ae60;">Similarity: {{ (suggestion.similarity * 100).toFixed(1) }}%</span>
                                <span style="font-size: 11px; color: var(--text-secondary);">IDs: {{ suggestion.source_id }} &rarr; {{ suggestion.target_id }}</span>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                                <div style="padding: 12px; background: var(--bg-surface); border-radius: 6px; border-left: 3px solid #3498db;">
                                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600;">Source</div>
                                    <div style="font-size: 13px; color: var(--text-primary);">{{ truncate(suggestion.source_content, 120) }}</div>
                                </div>
                                <div style="padding: 12px; background: var(--bg-surface); border-radius: 6px; border-left: 3px solid #9b59b6;">
                                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600;">Target</div>
                                    <div style="font-size: 13px; color: var(--text-primary);">{{ truncate(suggestion.target_content, 120) }}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </template>
                <div v-else class="empty-state" style="padding:30px 10px;">
                    <p class="muted text-sm">No link suggestions found.</p>
                </div>
            </div>
        </div>
    `,
});
