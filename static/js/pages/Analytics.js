/* ============================================================
   Megregore — Analytics Page (Vue Component)
   ============================================================ */

megregoreApp.component('analytics-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const analytics = ref({});
        const topAccessed = ref([]);
        const orphans = ref([]);

        const statCards = computed(() => [
            { label: 'Total Memories', value: analytics.value.total_memories || 0, className: '' },
            { label: 'Total Accesses', value: analytics.value.total_accesses || 0, className: 'accent' },
            { label: 'Avg Activation', value: ((analytics.value.avg_activation || 0) * 100).toFixed(1) + '%', className: 'teal' },
            { label: 'Orphan Count', value: analytics.value.orphan_count || 0, className: '' },
            { label: 'Threaded Count', value: analytics.value.threaded_count || 0, className: '' },
            { label: 'Thread Coverage', value: ((analytics.value.thread_coverage_pct || 0) * 100).toFixed(1) + '%', className: 'accent' },
        ]);

        const accessByTypeRows = computed(() => {
            const accessByType = analytics.value.access_by_type || {};
            if (!Object.keys(accessByType).length) return [];
            const counts = Object.values(accessByType);
            const maxCount = Math.max(...counts);
            return Object.entries(accessByType)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => ({
                    type,
                    count,
                    pct: Math.round((count / maxCount) * 100),
                }));
        });

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                const [analyticsData, topAccessedData, orphansData] = await Promise.all([
                    App.api('/analytics'),
                    App.api('/analytics/top-accessed', { days: 30, limit: 20 }),
                    App.api('/analytics/orphans', { min_age_days: 7, limit: 20 }),
                ]);

                analytics.value = analyticsData;
                topAccessed.value = topAccessedData.memories || [];
                orphans.value = orphansData.memories || [];
            } catch (err) {
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
            topAccessed,
            orphans,
            accessByTypeRows,
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
                <h1>Analytics</h1>
                <p>How your memories are being used</p>
            </div>

            <!-- Stat Cards -->
            <div class="stats-row">
                <div v-for="(card, i) in statCards" :key="card.label"
                     class="stat-card" :class="[card.className, 'fade-in', 'fade-in-delay-' + (i % 4 + 1)]">
                    <div class="stat-label">{{ card.label }}</div>
                    <div class="stat-value">{{ card.value }}</div>
                </div>
            </div>

            <!-- Two Column Layout -->
            <div class="two-col">
                <!-- Top Accessed -->
                <div class="section fade-in">
                    <div class="section-title">
                        Top Accessed
                        <span class="count">{{ topAccessed.length }}</span>
                    </div>
                    <template v-if="topAccessed.length">
                        <div v-for="m in topAccessed" :key="m.id" class="card" style="padding:14px 18px;">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                                <div style="flex: 1;">
                                    <div style="font-size: 13px; color: var(--text-primary); margin-bottom: 4px;">{{ truncate(m.content, 120) }}</div>
                                    <div style="display: flex; gap: 12px; align-items: center;">
                                        <span style="font-size: 12px; color: var(--text-muted);">Accessed {{ m.recent_access_count }} time{{ m.recent_access_count !== 1 ? 's' : '' }}</span>
                                        <span v-html="importanceBarHtml(m.importance)"></span>
                                    </div>
                                </div>
                            </div>
                            <div style="margin-top: 8px;">
                                <span style="font-size: 11px; color: var(--text-secondary); margin-right: 12px;">Activation</span>
                                <span v-html="activationBarHtml(m.activation_level)"></span>
                            </div>
                        </div>
                    </template>
                    <div v-else class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">No memories accessed recently.</p>
                    </div>
                </div>

                <!-- Orphan Memories -->
                <div class="section fade-in">
                    <div class="section-title">
                        Orphan Memories
                        <span class="count">{{ orphans.length }}</span>
                    </div>
                    <template v-if="orphans.length">
                        <div v-for="(m, idx) in orphans" :key="m.id" class="card" style="padding:14px 18px;">
                            <div style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center;">
                                <span v-html="typeBadgeHtml(m.memory_type)"></span>
                                <span style="font-size: 12px; color: var(--text-muted);">{{ formatDate(m.created_at) }}</span>
                            </div>
                            <div style="font-size: 13px; color: var(--text-primary);">{{ truncate(m.content, 120) }}</div>
                            <div v-if="m.tags && m.tags.length" style="margin-top: 6px;" v-html="tagPillsHtml(m.tags)"></div>
                        </div>
                    </template>
                    <div v-else class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">All memories are linked or recently accessed.</p>
                    </div>
                </div>
            </div>

            <!-- Access by Type Chart -->
            <div class="section fade-in">
                <div class="section-title">Access by Type</div>
                <div v-if="accessByTypeRows.length" class="card">
                    <div class="bar-chart">
                        <div v-for="row in accessByTypeRows" :key="row.type" class="bar-row">
                            <span class="bar-label">{{ row.type }}</span>
                            <span class="bar-track">
                                <span class="bar-fill" :style="{ width: row.pct + '%' }"></span>
                            </span>
                            <span class="bar-count">{{ row.count }}</span>
                        </div>
                    </div>
                </div>
                <div v-else class="empty-state" style="padding:30px 10px;">
                    <p class="muted text-sm">No access data yet.</p>
                </div>
            </div>
        </div>
    `,

    methods: {
        formatDate: App.formatDate,
        truncate: App.truncateText,
        typeBadgeHtml: App.typeBadge,
        importanceBarHtml: App.importanceBar,
        activationBarHtml: App.activationBar,
        tagPillsHtml: App.tagPills,
    },
});
