/* ============================================================
   Megregore — Self-Model Predictions Page (Vue Component)
   ============================================================ */

megregoreApp.component('self-model-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const accuracyData = ref(null);

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                const res = await App.api('/self-model/accuracy');
                accuracyData.value = res;
            } catch (err) {
                error.value = err.message;
            } finally {
                loading.value = false;
            }
        }

        onMounted(() => { loadData(); });

        function accuracyColor(score) {
            if (score > 0.7) return '#27ae60';
            if (score > 0.4) return '#f39c12';
            return '#e74c3c';
        }

        return { loading, error, accuracyData, accuracyColor };
    },
    template: `
        <div v-if="loading" class="loading"><div class="spinner"></div></div>
        <div v-else-if="error" class="empty-state fade-in">
            <h3>Something went wrong</h3>
            <p>{{ error }}</p>
        </div>
        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Self-Model Predictions</h1>
            </div>

            <div class="stat-grid">
                <div class="stat-card">
                    <div class="value">{{ accuracyData ? accuracyData.total_evaluated : '\u2014' }}</div>
                    <div class="label">Total Evaluated</div>
                </div>
                <div class="stat-card">
                    <div class="value" style="color: #27ae60;">{{ accuracyData ? accuracyData.verified : '\u2014' }}</div>
                    <div class="label">Verified</div>
                </div>
                <div class="stat-card">
                    <div class="value" style="color: #e74c3c;">{{ accuracyData ? accuracyData.falsified : '\u2014' }}</div>
                    <div class="label">Falsified</div>
                </div>
                <div class="stat-card">
                    <div class="value" :style="{ color: accuracyColor(accuracyData?.accuracy || 0) }">{{ accuracyData ? Math.round(accuracyData.accuracy * 100) + '%' : '\u2014' }}</div>
                    <div class="label">Accuracy</div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3>Prediction Stats</h3>
                </div>
                <div class="table-container">
                    <div v-if="accuracyData && accuracyData.total_evaluated > 0">
                        <table class="data-table">
                            <tbody>
                                <tr>
                                    <td>Average Surprise</td>
                                    <td>{{ (accuracyData.avg_surprise * 100).toFixed(1) + '%' }}</td>
                                </tr>
                                <tr>
                                    <td>Verification Rate</td>
                                    <td>{{ accuracyData.total_evaluated > 0 ? Math.round(accuracyData.verified / accuracyData.total_evaluated * 100) + '%' : '\u2014' }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <div v-else class="empty-state">
                        <p>No predictions evaluated yet. Use the <strong>predict_self</strong> MCP tool to make predictions about your own behavior.</p>
                    </div>
                </div>
            </div>
        </div>
    `
});
