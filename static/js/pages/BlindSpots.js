/* ============================================================
   Megregore — Blind Spots Page (Vue Component)
   ============================================================ */

megregoreApp.component('blind-spots-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const currentData = ref(null);

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                const res = await App.api('/blind-spots/current');
                currentData.value = res;
            } catch (err) {
                error.value = err.message;
            } finally {
                loading.value = false;
            }
        }

        onMounted(() => { loadData(); });

        function coverageColor(score) {
            if (score > 0.8) return '#27ae60';
            if (score > 0.5) return '#f39c12';
            return '#e74c3c';
        }

        function severityColor(severity) {
            if (severity > 0.7) return '#e74c3c';
            if (severity > 0.4) return '#f39c12';
            return '#27ae60';
        }

        return { loading, error, currentData, coverageColor, severityColor };
    },
    template: `
        <div v-if="loading" class="loading"><div class="spinner"></div></div>
        <div v-else-if="error" class="empty-state fade-in">
            <h3>Something went wrong</h3>
            <p>{{ error }}</p>
        </div>
        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Blind Spots</h1>
            </div>

            <div class="stat-grid">
                <div class="stat-card">
                    <div class="value" :style="{ color: coverageColor(currentData?.coverage_score || 0) }">{{ currentData ? Math.round(currentData.coverage_score * 100) + '%' : '\u2014' }}</div>
                    <div class="label">Coverage Score</div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3>Neglected Threads</h3>
                </div>
                <div class="table-container">
                    <table class="data-table" v-if="currentData?.neglected_threads?.length > 0">
                        <thead>
                            <tr>
                                <th>Title</th>
                                <th>Memories</th>
                                <th>Days Silent</th>
                                <th>Severity</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="thread in currentData.neglected_threads" :key="thread.thread_id">
                                <td>{{ App.truncateText(thread.title, 40) }}</td>
                                <td>{{ thread.memory_count }}</td>
                                <td>{{ thread.days_silent }}</td>
                                <td>
                                    <div style="background: var(--bg-tertiary); height: 8px; border-radius: 4px; width: 100px; overflow: hidden;">
                                        <div :style="{ width: (thread.severity * 100) + '%', background: severityColor(thread.severity), height: '100%' }"></div>
                                    </div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                    <div v-else class="empty-state">
                        <p>No neglected threads found. All threads are being actively engaged.</p>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3>Topic Deserts</h3>
                </div>
                <div class="table-container">
                    <table class="data-table" v-if="currentData?.topic_deserts?.length > 0">
                        <thead>
                            <tr>
                                <th>Tag</th>
                                <th>Baseline</th>
                                <th>Recent</th>
                                <th>Drop</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="desert in currentData.topic_deserts" :key="desert.tag">
                                <td><span style="display: inline-block; padding: 2px 8px; background: var(--bg-tertiary); border-radius: 12px; font-size: 12px;">{{ desert.tag }}</span></td>
                                <td>{{ desert.baseline_count }}</td>
                                <td>{{ desert.recent_count }}</td>
                                <td style="color: #e74c3c;">{{ (desert.drop_ratio * 100).toFixed(0) + '%' }}</td>
                            </tr>
                        </tbody>
                    </table>
                    <div v-else class="empty-state">
                        <p>No topic deserts detected. Tag usage is consistent.</p>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3>Emotional Avoidance</h3>
                </div>
                <div class="table-container">
                    <table class="data-table" v-if="currentData?.emotional_avoidance?.length > 0">
                        <thead>
                            <tr>
                                <th>Title</th>
                                <th>Avg Emotion</th>
                                <th>Recent / Older</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="item in currentData.emotional_avoidance" :key="item.thread_id">
                                <td>{{ App.truncateText(item.title, 40) }}</td>
                                <td style="color: #e74c3c;">{{ item.avg_emotion.toFixed(2) }}</td>
                                <td>{{ item.recent_count }} / {{ item.older_count }}</td>
                            </tr>
                        </tbody>
                    </table>
                    <div v-else class="empty-state">
                        <p>No emotional avoidance patterns detected.</p>
                    </div>
                </div>
            </div>
        </div>
    `
});
