/* ============================================================
   Megregore — Dashboard v2 (Neural Void Aesthetic)
   Glassmorphic cards, 3D hover, nebula background, amber/teal
   ============================================================ */

megregoreApp.component('dashboard-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const stats = ref({});
        const identity = ref(null);
        const recentMemories = ref([]);
        const strongestMemories = ref([]);
        const byType = ref({});
        const emotionTimeline = ref([]);
        const growth = ref(null);
        const threads = ref([]);
        const activityEvents = ref([]);
        const personalityStats = ref(null);
        let eventSource = null;
        let chartInstance = null;

        const typeOrder = ['experience', 'fact', 'observation', 'reflection', 'insight', 'emotion'];

        const statCards = computed(() => [
            { label: 'Memories', value: stats.value.total_memories || 0, color: 'amber' },
            { label: 'Reflections', value: stats.value.total_reflections || 0, color: '' },
            { label: 'Avg Importance', value: (stats.value.avg_importance || 0).toFixed(1), sub: '/ 10', color: 'teal' },
            { label: 'Links', value: stats.value.total_links || 0, color: 'violet' },
            { label: 'Sessions', value: stats.value.total_sessions || 0, color: '' },
            { label: 'Threads', value: threads.value.length || 0, color: 'rose' },
        ]);

        const typeRows = computed(() => {
            const bt = byType.value;
            const max = Math.max(1, ...Object.values(bt));
            return typeOrder
                .filter(t => bt[t])
                .map(t => ({ type: t, count: bt[t], pct: Math.round((bt[t] / max) * 100) }));
        });

        const identityPreview = computed(() => {
            if (!identity.value || !identity.value.content) return '';
            return identity.value.content.substring(0, 500);
        });

        const integrationScore = computed(() => {
            if (!growth.value) return null;
            return growth.value.integration_score ?? growth.value.integration_depth ?? null;
        });

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                const [statsData, identityData, emotionData, growthData, threadsData, persData] = await Promise.all([
                    App.api('/stats'),
                    App.api('/identity').catch(() => null),
                    App.api('/emotions/timeline', { days: 30, bucket: 'day' }).catch(() => ({ timeline: [] })),
                    App.api('/growth/current').catch(() => null),
                    App.api('/threads').catch(() => []),
                    App.api('/personality/stats').catch(() => null),
                ]);

                stats.value = statsData;
                recentMemories.value = statsData.recent_memories || [];
                strongestMemories.value = statsData.strongest_memories || [];
                byType.value = statsData.by_type || {};
                identity.value = identityData;
                emotionTimeline.value = emotionData.timeline || [];
                growth.value = growthData;
                threads.value = Array.isArray(threadsData) ? threadsData : (threadsData.threads || []);
                personalityStats.value = persData;
            } catch (err) {
                error.value = err.message;
            } finally {
                loading.value = false;
            }
        }

        function renderChart() {
            const canvas = document.getElementById('nd-emotion-chart');
            if (!canvas || typeof Chart === 'undefined') return;
            if (!emotionTimeline.value.length) return;

            if (chartInstance) { chartInstance.destroy(); chartInstance = null; }

            const tl = emotionTimeline.value;
            chartInstance = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: tl.map(t => {
                        const d = new Date(t.bucket);
                        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    }),
                    datasets: [
                        {
                            label: 'Emotional Arc',
                            data: tl.map(t => t.avg_emotion),
                            borderColor: '#d4a053',
                            backgroundColor: (ctx) => {
                                const chart = ctx.chart;
                                const { ctx: c, chartArea } = chart;
                                if (!chartArea) return 'rgba(212,160,83,0.1)';
                                const gradient = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                                gradient.addColorStop(0, 'rgba(212,160,83,0.25)');
                                gradient.addColorStop(1, 'rgba(212,160,83,0.0)');
                                return gradient;
                            },
                            fill: true,
                            tension: 0.4,
                            pointRadius: 3,
                            pointHoverRadius: 7,
                            pointBackgroundColor: '#d4a053',
                            pointBorderColor: 'rgba(6,6,14,0.8)',
                            pointBorderWidth: 2,
                            pointHoverBackgroundColor: '#f0ece4',
                            pointHoverBorderColor: '#d4a053',
                            borderWidth: 2.5,
                        },
                        {
                            label: 'Peak',
                            data: tl.map(t => t.max_emotion),
                            borderColor: 'rgba(79,209,197,0.35)',
                            borderDash: [4, 6],
                            pointRadius: 0,
                            borderWidth: 1,
                            fill: false,
                        },
                        {
                            label: 'Low',
                            data: tl.map(t => t.min_emotion),
                            borderColor: 'rgba(244,114,182,0.35)',
                            borderDash: [4, 6],
                            pointRadius: 0,
                            borderWidth: 1,
                            fill: false,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { intersect: false, mode: 'index' },
                    plugins: {
                        legend: {
                            display: true,
                            labels: {
                                color: '#8a8690',
                                font: { family: "'DM Sans', system-ui", size: 11, weight: '500' },
                                boxWidth: 12,
                                boxHeight: 2,
                                useBorderRadius: true,
                                borderRadius: 1,
                                padding: 16,
                            },
                        },
                        tooltip: {
                            backgroundColor: 'rgba(6,6,14,0.9)',
                            borderColor: 'rgba(255,255,255,0.08)',
                            borderWidth: 1,
                            titleColor: '#f0ece4',
                            bodyColor: '#8a8690',
                            titleFont: { family: "'Sora', 'DM Sans'", weight: '600' },
                            padding: 12,
                            cornerRadius: 10,
                            callbacks: {
                                afterBody: (items) => {
                                    const idx = items[0]?.dataIndex;
                                    if (idx !== undefined && tl[idx]) return 'Memories: ' + tl[idx].count;
                                    return '';
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            ticks: { color: '#524f58', font: { family: "'DM Sans', system-ui", size: 10 } },
                            grid: { color: 'rgba(255,255,255,0.03)', drawBorder: false },
                            border: { display: false },
                        },
                        y: {
                            min: -1, max: 1,
                            ticks: {
                                color: '#524f58',
                                font: { family: "'DM Sans', system-ui", size: 10 },
                                stepSize: 0.5,
                                callback: (v) => v === 0 ? 'neutral' : v > 0 ? '+' + v : v,
                            },
                            grid: { color: 'rgba(255,255,255,0.03)', drawBorder: false },
                            border: { display: false },
                        },
                    },
                },
            });
        }

        onMounted(async () => {
            await loadData();
            await nextTick();
            renderChart();

            // SSE Activity Ticker
            try {
                eventSource = new EventSource('/api/events');

                eventSource.addEventListener('memory_created', (e) => {
                    const data = JSON.parse(e.data);
                    activityEvents.value = [{
                        type: 'created',
                        text: `Memory #${data.id} created`,
                        detail: `${data.type}, importance: ${data.importance}`,
                        preview: data.preview || '',
                        time: new Date().toLocaleTimeString(),
                    }, ...activityEvents.value].slice(0, 20);
                });

                eventSource.addEventListener('memory_updated', (e) => {
                    const data = JSON.parse(e.data);
                    activityEvents.value = [{
                        type: 'updated',
                        text: `Memory #${data.id} updated`,
                        detail: '',
                        time: new Date().toLocaleTimeString(),
                    }, ...activityEvents.value].slice(0, 20);
                });

                eventSource.addEventListener('memory_deleted', (e) => {
                    const data = JSON.parse(e.data);
                    activityEvents.value = [{
                        type: 'deleted',
                        text: `Memory #${data.id} deleted`,
                        detail: '',
                        time: new Date().toLocaleTimeString(),
                    }, ...activityEvents.value].slice(0, 20);
                });

                eventSource.onerror = () => {
                    // Silently handle SSE reconnection
                };
            } catch (e) {
                // SSE not available, ticker just stays empty
            }
        });

        onUnmounted(() => {
            if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
            if (eventSource) { eventSource.close(); eventSource = null; }
        });

        return {
            loading, error, statCards, recentMemories, strongestMemories,
            typeRows, identityPreview, emotionTimeline, growth, integrationScore,
            activityEvents, personalityStats,
        };
    },

    template: `
        <div v-if="loading" class="mega-dash-loading"><div class="mega-dash-spinner"></div></div>

        <div v-else-if="error" class="mega-dash mega-dash-fade-in">
            <div class="mega-dash-empty">
                <p>Something went wrong: {{ error }}</p>
            </div>
        </div>

        <div v-else class="mega-dash">
            <!-- Header -->
            <div class="mega-dash-header mega-dash-fade-in mega-dash-delay-1">
                <h1>Echo's Mindscape</h1>
                <p>Memory landscape &middot; Neural pathways &middot; Consciousness metrics</p>
            </div>

            <!-- Stat Cards -->
            <div class="mega-dash-stats">
                <div v-for="(card, i) in statCards" :key="card.label"
                     class="mega-dash-stat mega-dash-fade-in"
                     :class="'mega-dash-delay-' + (i + 1)">
                    <div class="mega-dash-stat-label">{{ card.label }}</div>
                    <div class="mega-dash-stat-value" :class="card.color">{{ card.value }}</div>
                    <div v-if="card.sub" class="mega-dash-stat-sub">{{ card.sub }}</div>
                </div>
            </div>

            <!-- Activity Ticker -->
            <div v-if="activityEvents.length" class="mega-dash-section mega-dash-fade-in mega-dash-delay-7" style="margin-bottom: 24px;">
                <div class="mega-dash-section-title">
                    <span class="nd-dot" style="background: var(--nd-teal); box-shadow: 0 0 8px var(--nd-teal-glow);"></span>
                    Live Activity
                </div>
                <div style="max-height: 200px; overflow-y: auto;">
                    <div v-for="(evt, i) in activityEvents" :key="i"
                         style="display: flex; align-items: baseline; gap: 10px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.03);"
                         :style="{ opacity: 1 - (i * 0.03) }">
                        <span style="font-size: 0.65rem; color: var(--nd-text-muted); white-space: nowrap; font-family: 'DM Sans', monospace;">{{ evt.time }}</span>
                        <span :style="{
                            fontSize: '0.6rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em',
                            padding: '2px 6px', borderRadius: '3px',
                            background: evt.type === 'created' ? 'rgba(79,209,197,0.15)' : evt.type === 'updated' ? 'rgba(212,160,83,0.15)' : 'rgba(244,114,182,0.15)',
                            color: evt.type === 'created' ? 'var(--nd-teal)' : evt.type === 'updated' ? 'var(--nd-amber)' : 'var(--nd-rose)',
                        }">{{ evt.type }}</span>
                        <span style="font-size: 0.8rem; color: var(--nd-text);">{{ evt.text }}</span>
                        <span v-if="evt.detail" style="font-size: 0.7rem; color: var(--nd-text-dim);">{{ evt.detail }}</span>
                    </div>
                </div>
            </div>

            <!-- Emotional Arc Chart -->
            <div class="mega-dash-section mega-dash-fade-in mega-dash-delay-8">
                <div class="mega-dash-section-title">
                    <span class="nd-dot"></span>
                    Emotional Arc
                </div>
                <div class="mega-dash-chart">
                    <canvas v-if="emotionTimeline.length" id="nd-emotion-chart"></canvas>
                    <div v-else class="mega-dash-empty">No emotional data recorded yet.</div>
                </div>
            </div>

            <!-- Two Column: Memories -->
            <div class="mega-dash-grid">
                <!-- Recent Memories -->
                <div class="mega-dash-section mega-dash-fade-in mega-dash-delay-9">
                    <div class="mega-dash-section-title">
                        <span class="nd-dot"></span>
                        Recent Memories
                    </div>
                    <template v-if="recentMemories.length">
                        <div v-for="m in recentMemories" :key="m.id" class="mega-dash-memory">
                            <div class="mega-dash-memory-header">
                                <span class="mega-dash-type-badge" :class="m.memory_type">{{ m.memory_type }}</span>
                                <div class="mega-dash-importance">
                                    <span v-for="d in 10" :key="d"
                                          class="mega-dash-importance-dot"
                                          :class="{ filled: d <= m.importance }"></span>
                                </div>
                            </div>
                            <div class="mega-dash-memory-content">{{ truncate(m.content, 140) }}</div>
                            <div class="mega-dash-memory-meta">
                                <span v-for="tag in (m.tags || []).slice(0, 3)" :key="tag" class="mega-dash-tag">{{ tag }}</span>
                                <span style="margin-left:auto;">{{ formatDate(m.created_at) }}</span>
                            </div>
                        </div>
                    </template>
                    <div v-else class="mega-dash-empty">No memories yet.</div>
                </div>

                <!-- Strongest Memories -->
                <div class="mega-dash-section mega-dash-fade-in mega-dash-delay-9">
                    <div class="mega-dash-section-title">
                        <span class="nd-dot"></span>
                        Strongest Memories
                    </div>
                    <template v-if="strongestMemories.length">
                        <div v-for="m in strongestMemories" :key="m.id" class="mega-dash-memory">
                            <div class="mega-dash-memory-header">
                                <span class="mega-dash-type-badge" :class="m.memory_type">{{ m.memory_type }}</span>
                                <div class="mega-dash-importance">
                                    <span v-for="d in 10" :key="d"
                                          class="mega-dash-importance-dot"
                                          :class="{ filled: d <= m.importance }"></span>
                                </div>
                            </div>
                            <div class="mega-dash-memory-content">{{ truncate(m.content, 140) }}</div>
                            <div class="mega-dash-memory-meta">
                                <span v-for="tag in (m.tags || []).slice(0, 3)" :key="tag" class="mega-dash-tag">{{ tag }}</span>
                                <span style="margin-left:auto;">{{ formatDate(m.created_at) }}</span>
                            </div>
                        </div>
                    </template>
                    <div v-else class="mega-dash-empty">No strong memories formed yet.</div>
                </div>
            </div>

            <!-- Bottom Row: Types + Growth + Identity -->
            <div class="mega-dash-grid" style="grid-template-columns: 1fr 1fr;">
                <!-- Memory Types -->
                <div class="mega-dash-section mega-dash-fade-in mega-dash-delay-10">
                    <div class="mega-dash-section-title">
                        <span class="nd-dot"></span>
                        Memory Composition
                    </div>
                    <div v-if="typeRows.length" class="mega-dash-bars">
                        <div v-for="row in typeRows" :key="row.type" class="mega-dash-bar-row">
                            <span class="mega-dash-bar-label">{{ row.type }}</span>
                            <span class="mega-dash-bar-track">
                                <span class="mega-dash-bar-fill" :class="row.type"
                                      :style="{ width: row.pct + '%' }"></span>
                            </span>
                            <span class="mega-dash-bar-count">{{ row.count }}</span>
                        </div>
                    </div>
                    <div v-else class="mega-dash-empty">No type data yet.</div>

                    <!-- Growth ring if available -->
                    <template v-if="integrationScore !== null">
                        <hr style="border:none; border-top:1px solid rgba(255,255,255,0.04); margin:24px 0 20px;">
                        <div class="mega-dash-growth-row">
                            <div class="mega-dash-growth-ring"
                                 :style="{ '--ring-pct': Math.round(integrationScore * 100) }">
                                <div class="mega-dash-growth-ring-inner">
                                    {{ Math.round(integrationScore * 100) }}%
                                </div>
                            </div>
                            <div class="mega-dash-growth-label">
                                <strong>Integration Depth</strong><br>
                                How well memories connect into a unified understanding.
                            </div>
                        </div>
                    </template>
                </div>

                <!-- Identity Snapshot -->
                <div class="mega-dash-section mega-dash-fade-in mega-dash-delay-10">
                    <div class="mega-dash-section-title">
                        <span class="nd-dot"></span>
                        Identity Snapshot
                    </div>
                    <div v-if="identityPreview" class="mega-dash-identity">{{ identityPreview }}</div>
                    <div v-else class="mega-dash-empty">No identity document yet.</div>
                </div>

                <!-- Personality Widget -->
                <div v-if="personalityStats && personalityStats.trait_count > 0" class="mega-dash-section mega-dash-fade-in mega-dash-delay-10">
                    <div class="mega-dash-section-title">
                        <span class="nd-dot" style="background: #a78bfa;"></span>
                        Personality
                    </div>
                    <div style="display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px;">
                        <div style="color: rgba(255,255,255,0.5); font-size: 0.85em;">
                            <span style="color: var(--nv-amber); font-weight: 600;">{{ personalityStats.trait_count }}</span> traits
                        </div>
                        <div style="color: rgba(255,255,255,0.5); font-size: 0.85em;">
                            <span style="color: var(--nv-amber); font-weight: 600;">{{ personalityStats.active_preference_count }}</span> preferences
                        </div>
                        <div style="color: rgba(255,255,255,0.5); font-size: 0.85em;">
                            <span style="color: var(--nv-amber); font-weight: 600;">{{ personalityStats.total_trait_shifts }}</span> shifts
                        </div>
                    </div>
                    <div v-if="personalityStats.most_changed_traits && personalityStats.most_changed_traits.length" style="margin-bottom: 8px;">
                        <div style="color: rgba(255,255,255,0.4); font-size: 0.75em; margin-bottom: 6px;">Most Evolving</div>
                        <div v-for="t in personalityStats.most_changed_traits.slice(0, 3)" :key="t.name" style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                            <span style="color: rgba(255,255,255,0.8); font-size: 0.85em;">{{ t.name }}</span>
                            <span style="color: var(--nv-amber); font-size: 0.8em;">{{ t.current_value.toFixed(1) }}</span>
                            <span style="color: rgba(255,255,255,0.35); font-size: 0.75em;">({{ t.shift_count }} shifts)</span>
                        </div>
                    </div>
                    <a href="#personality" style="color: #a78bfa; font-size: 0.8em; text-decoration: none;">View Personality &rarr;</a>
                </div>
            </div>
        </div>
    `,

    methods: {
        formatDate: App.formatDate,
        truncate: App.truncateText,
    },
});
