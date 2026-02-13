/* ============================================================
   Megregore — Growth Metrics Page (Vue Component)
   ============================================================ */

megregoreApp.component('growth-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const currentData = ref(null);
        const trajectoryData = ref([]);

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                const [currentRes, trajectoryRes] = await Promise.all([
                    App.api('/growth/current'),
                    App.api('/growth/trajectory', { limit: 10 })
                ]);
                currentData.value = currentRes;
                trajectoryData.value = trajectoryRes.snapshots || [];
            } catch (err) {
                error.value = err.message;
            } finally {
                loading.value = false;
            }
        }

        onMounted(() => { loadData(); });

        function scoreColor(score) {
            if (score > 0.7) return '#27ae60';
            if (score > 0.4) return '#f39c12';
            return '#e74c3c';
        }

        function formatDelta(delta) {
            const pct = (delta * 100).toFixed(1);
            return (delta >= 0 ? '+' : '') + pct + '%';
        }

        return { loading, error, currentData, trajectoryData, scoreColor, formatDelta, formatDate: App.formatDate };
    },
    template: `
        <div v-if="loading" class="loading"><div class="spinner"></div></div>
        <div v-else-if="error" class="empty-state fade-in">
            <h3>Something went wrong</h3>
            <p>{{ error }}</p>
        </div>
        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Growth Metrics</h1>
            </div>

            <div class="stat-grid">
                <div class="stat-card">
                    <div class="value" :style="{ color: scoreColor(currentData?.integration_score || 0) }">{{ currentData ? Math.round(currentData.integration_score * 100) + '%' : '\u2014' }}</div>
                    <div class="label">Integration Score</div>
                </div>
                <div class="stat-card">
                    <div class="value">{{ currentData ? currentData.resolved_contradictions + '/' + currentData.total_contradictions : '\u2014' }}</div>
                    <div class="label">Contradictions Resolved</div>
                </div>
                <div class="stat-card">
                    <div class="value" :style="{ color: scoreColor(currentData?.resolution_rate || 0) }">{{ currentData ? Math.round(currentData.resolution_rate * 100) + '%' : '\u2014' }}</div>
                    <div class="label">Resolution Rate</div>
                </div>
                <div class="stat-card">
                    <div class="value" :style="{ color: scoreColor(currentData?.thread_coverage_pct || 0) }">{{ currentData ? Math.round(currentData.thread_coverage_pct * 100) + '%' : '\u2014' }}</div>
                    <div class="label">Thread Coverage</div>
                </div>
                <div class="stat-card">
                    <div class="value">{{ currentData ? currentData.cross_thread_link_count : '\u2014' }}</div>
                    <div class="label">Cross-Thread Links</div>
                </div>
                <div class="stat-card">
                    <div class="value">{{ currentData ? currentData.emotional_range : '\u2014' }}</div>
                    <div class="label">Emotional Range</div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3>Growth Details</h3>
                </div>
                <div class="table-container">
                    <table class="data-table">
                        <tbody>
                            <tr>
                                <td>Avg Links per Memory</td>
                                <td>{{ currentData ? currentData.avg_links_per_memory.toFixed(2) : '\u2014' }}</td>
                            </tr>
                            <tr>
                                <td>Consolidation Ratio</td>
                                <td>{{ currentData ? (currentData.consolidation_ratio * 100).toFixed(1) + '%' : '\u2014' }}</td>
                            </tr>
                            <tr>
                                <td>Unique Topics</td>
                                <td>{{ currentData ? currentData.unique_topic_count : '\u2014' }}</td>
                            </tr>
                            <tr>
                                <td>Integration Delta</td>
                                <td>{{ currentData ? formatDelta(currentData.integration_delta) : '\u2014' }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3>Growth Trajectory</h3>
                </div>
                <div class="table-container">
                    <table class="data-table" v-if="trajectoryData.length > 0">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Integration Score</th>
                                <th>Delta</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="snapshot in trajectoryData" :key="snapshot.created_at">
                                <td>{{ formatDate(snapshot.created_at) }}</td>
                                <td :style="{ color: scoreColor(snapshot.integration_score) }">{{ (snapshot.integration_score * 100).toFixed(1) + '%' }}</td>
                                <td>{{ formatDelta(snapshot.integration_delta) }}</td>
                            </tr>
                        </tbody>
                    </table>
                    <div v-else class="empty-state">
                        <p>No trajectory data yet. Growth snapshots are generated every 3 days.</p>
                    </div>
                </div>
            </div>
        </div>
    `
});
