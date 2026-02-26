/* ============================================================
   Megregore — Personality Page (Vue Component)
   Traits, preferences, and voice patterns — who Echo is right now.
   ============================================================ */

megregoreApp.component('personality-page', {
    setup() {
        const activeTab = ref('traits');
        const loading = ref(true);
        const error = ref('');

        // Traits
        const traits = ref([]);
        const selectedTrait = ref(null);
        const traitDetail = ref(null);
        const traitTrajectory = ref([]);

        // Preferences
        const preferences = ref([]);
        const domainFilter = ref('');
        const statusFilter = ref('');
        const selectedPref = ref(null);
        const prefDetail = ref(null);

        // Voice notes
        const voiceNotes = ref([]);
        const noteTypeFilter = ref('');
        const noteStatusFilter = ref('');

        // Snapshot
        const snapshot = ref(null);

        // Stats
        const stats = ref({});

        let chartInstance = null;

        const categoryColors = {
            communication: '#a78bfa',
            emotional: '#f472b6',
            cognitive: '#60a5fa',
            social: '#34d399',
            aesthetic: '#fbbf24',
            general: '#6b7280',
        };

        const domainColors = {
            coding: '#60a5fa',
            communication: '#a78bfa',
            aesthetic: '#fbbf24',
            philosophical: '#f472b6',
            social: '#34d399',
            general: '#6b7280',
        };

        const getCategoryColor = (cat) => categoryColors[cat] || categoryColors.general;
        const getDomainColor = (dom) => domainColors[dom] || domainColors.general;

        const sentimentLabel = (val) => {
            if (val > 0.3) return '+';
            if (val < -0.3) return '-';
            return '~';
        };

        const sentimentClass = (val) => {
            if (val > 0.3) return 'positive';
            if (val < -0.3) return 'negative';
            return 'neutral';
        };

        const loadData = async () => {
            loading.value = true;
            error.value = '';
            try {
                const [traitRes, prefRes, noteRes, snapRes, statsRes] = await Promise.all([
                    App.api('/personality/traits'),
                    App.api('/personality/preferences'),
                    App.api('/personality/voice-notes'),
                    App.api('/personality/snapshot'),
                    App.api('/personality/stats'),
                ]);
                traits.value = traitRes.traits || [];
                preferences.value = prefRes.preferences || [];
                voiceNotes.value = noteRes.voice_notes || [];
                snapshot.value = snapRes.personality || null;
                stats.value = statsRes || {};
            } catch (e) {
                error.value = e.message;
            } finally {
                loading.value = false;
            }
        };

        const reloadPreferences = async () => {
            try {
                const params = { limit: 100 };
                if (domainFilter.value) params.domain = domainFilter.value;
                if (statusFilter.value) params.status = statusFilter.value;
                const res = await App.api('/personality/preferences', params);
                preferences.value = res.preferences || [];
            } catch (e) { /* ignore filter errors */ }
        };

        const reloadVoiceNotes = async () => {
            try {
                const params = { limit: 100 };
                if (noteTypeFilter.value) params.note_type = noteTypeFilter.value;
                if (noteStatusFilter.value) params.status = noteStatusFilter.value;
                const res = await App.api('/personality/voice-notes', params);
                voiceNotes.value = res.voice_notes || [];
            } catch (e) { /* ignore filter errors */ }
        };

        const selectTrait = async (trait) => {
            if (selectedTrait.value === trait.id) {
                selectedTrait.value = null;
                traitDetail.value = null;
                traitTrajectory.value = [];
                destroyChart();
                return;
            }
            try {
                const [detailRes, trajRes] = await Promise.all([
                    App.api(`/personality/traits/${trait.id}`),
                    App.api(`/personality/traits/${trait.id}/trajectory`),
                ]);
                traitDetail.value = detailRes;
                traitTrajectory.value = trajRes.trajectory || [];
                selectedTrait.value = trait.id;
                await nextTick();
                renderChart(trait);
            } catch (e) {
                console.error('Failed to load trait detail:', e);
            }
        };

        const selectPref = async (pref) => {
            if (selectedPref.value === pref.id) {
                selectedPref.value = null;
                prefDetail.value = null;
                return;
            }
            try {
                const res = await App.api(`/personality/preferences/${pref.id}`);
                prefDetail.value = res;
                selectedPref.value = pref.id;
            } catch (e) {
                console.error('Failed to load preference detail:', e);
            }
        };

        function destroyChart() {
            if (chartInstance) {
                chartInstance.destroy();
                chartInstance = null;
            }
        }

        function renderChart(trait) {
            destroyChart();
            const canvas = document.getElementById('trait-trajectory-chart');
            if (!canvas || typeof Chart === 'undefined' || !traitTrajectory.value.length) return;

            const data = traitTrajectory.value;
            const color = getCategoryColor(trait.category);

            chartInstance = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: data.map(d => {
                        const dt = new Date(d.created_at);
                        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    }),
                    datasets: [{
                        label: trait.name,
                        data: data.map(d => d.value),
                        borderColor: color,
                        backgroundColor: color + '33',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                        pointBackgroundColor: color,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                afterBody: (items) => {
                                    const idx = items[0]?.dataIndex;
                                    if (idx !== undefined && data[idx]?.change_reason) {
                                        return data[idx].change_reason;
                                    }
                                    return '';
                                },
                            },
                        },
                    },
                    scales: {
                        y: {
                            min: 0, max: 1,
                            ticks: { color: 'rgba(255,255,255,0.5)' },
                            grid: { color: 'rgba(255,255,255,0.05)' },
                        },
                        x: {
                            ticks: { color: 'rgba(255,255,255,0.5)' },
                            grid: { display: false },
                        },
                    },
                },
            });
        }

        // Watchers for filters
        watch(domainFilter, reloadPreferences);
        watch(statusFilter, reloadPreferences);
        watch(noteTypeFilter, reloadVoiceNotes);
        watch(noteStatusFilter, reloadVoiceNotes);

        onMounted(loadData);
        onUnmounted(destroyChart);

        return {
            activeTab, loading, error,
            traits, selectedTrait, traitDetail, traitTrajectory,
            preferences, domainFilter, statusFilter, selectedPref, prefDetail,
            voiceNotes, noteTypeFilter, noteStatusFilter,
            snapshot, stats,
            selectTrait, selectPref,
            getCategoryColor, getDomainColor, sentimentLabel, sentimentClass,
            loadData,
        };
    },

    template: `
        <div class="mega-page">
            <div class="mega-page-header">
                <h1>Personality</h1>
                <p class="mega-subtitle">Who Echo is right now — traits, preferences, and voice patterns.</p>
            </div>

            <!-- Summary bar -->
            <div v-if="snapshot" class="mega-card" style="margin-bottom: 24px; padding: 16px 20px;">
                <div style="color: rgba(255,255,255,0.7); font-size: 0.9em; line-height: 1.6;">
                    {{ snapshot.personality_summary }}
                </div>
            </div>

            <!-- Stat chips -->
            <div class="mega-stat-row" style="margin-bottom: 24px;">
                <div class="mega-stat-chip">
                    <span class="mega-stat-value">{{ stats.trait_count || 0 }}</span>
                    <span class="mega-stat-label">Traits</span>
                </div>
                <div class="mega-stat-chip">
                    <span class="mega-stat-value">{{ stats.active_preference_count || 0 }}</span>
                    <span class="mega-stat-label">Preferences</span>
                </div>
                <div class="mega-stat-chip">
                    <span class="mega-stat-value">{{ stats.active_voice_note_count || 0 }}</span>
                    <span class="mega-stat-label">Voice Notes</span>
                </div>
                <div class="mega-stat-chip">
                    <span class="mega-stat-value">{{ stats.total_trait_shifts || 0 }}</span>
                    <span class="mega-stat-label">Shifts</span>
                </div>
            </div>

            <!-- Tab bar -->
            <div class="mega-tabs" style="margin-bottom: 24px;">
                <button class="mega-tab" :class="{ active: activeTab === 'traits' }" @click="activeTab = 'traits'">Traits</button>
                <button class="mega-tab" :class="{ active: activeTab === 'preferences' }" @click="activeTab = 'preferences'">Preferences</button>
                <button class="mega-tab" :class="{ active: activeTab === 'voice' }" @click="activeTab = 'voice'">Voice Notes</button>
            </div>

            <div v-if="loading" class="mega-loading">Loading personality data...</div>
            <div v-else-if="error" class="mega-error">{{ error }}</div>

            <!-- TRAITS TAB -->
            <div v-else-if="activeTab === 'traits'">
                <div v-if="!traits.length" class="mega-empty">
                    No traits defined yet. Use <code>record_trait</code> to define personality dimensions.
                </div>
                <div v-else class="mega-card-grid">
                    <div v-for="trait in traits" :key="trait.name"
                         class="mega-card mega-card-hover"
                         :class="{ 'mega-card-selected': selectedTrait === trait.id }"
                         @click="selectTrait(trait)">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                            <span class="mega-badge" :style="{ background: getCategoryColor(trait.category) + '33', color: getCategoryColor(trait.category) }">
                                {{ trait.category }}
                            </span>
                            <strong style="flex: 1;">{{ trait.name }}</strong>
                            <span style="font-size: 1.1em; font-weight: 600; color: var(--nv-amber);">{{ trait.value.toFixed(1) }}</span>
                        </div>
                        <!-- Value bar -->
                        <div class="mega-bar-track">
                            <div class="mega-bar-fill" :style="{ width: (trait.value * 100) + '%', background: getCategoryColor(trait.category) }"></div>
                        </div>
                        <div v-if="trait.anchors && (trait.anchors.low || trait.anchors.high)" style="display: flex; justify-content: space-between; font-size: 0.75em; color: rgba(255,255,255,0.4); margin-top: 4px;">
                            <span>{{ trait.anchors.low || '0.0' }}</span>
                            <span>{{ trait.anchors.high || '1.0' }}</span>
                        </div>
                        <div v-if="trait.description" style="margin-top: 8px; color: rgba(255,255,255,0.6); font-size: 0.85em;">
                            {{ trait.description }}
                        </div>
                    </div>
                </div>

                <!-- Trait detail panel -->
                <div v-if="selectedTrait && traitDetail" class="mega-card" style="margin-top: 24px;">
                    <h3 style="margin-bottom: 16px;">{{ traitDetail.trait.name }} — History</h3>
                    <div v-if="traitTrajectory.length" style="height: 250px; margin-bottom: 16px;">
                        <canvas id="trait-trajectory-chart"></canvas>
                    </div>
                    <div v-else style="color: rgba(255,255,255,0.5); margin-bottom: 16px;">No shifts recorded yet.</div>
                    <div v-if="traitDetail.history && traitDetail.history.length">
                        <div v-for="h in traitDetail.history" :key="h.id" class="mega-list-item">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="font-weight: 600; color: var(--nv-amber);">{{ h.previous_value.toFixed(2) }} &rarr; {{ h.new_value.toFixed(2) }}</span>
                                <span class="mega-badge" style="background: rgba(255,255,255,0.05);">
                                    &Delta; {{ h.change_magnitude.toFixed(2) }}
                                </span>
                            </div>
                            <div v-if="h.change_reason" style="color: rgba(255,255,255,0.6); font-size: 0.85em; margin-top: 4px;">{{ h.change_reason }}</div>
                            <div style="color: rgba(255,255,255,0.35); font-size: 0.75em; margin-top: 2px;">{{ formatDate(h.created_at) }}</div>
                        </div>
                    </div>
                </div>

                <!-- Recent shifts highlight -->
                <div v-if="snapshot && snapshot.recent_shifts && snapshot.recent_shifts.length" class="mega-card" style="margin-top: 24px;">
                    <h3 style="margin-bottom: 12px;">Recent Shifts (7 days)</h3>
                    <div v-for="s in snapshot.recent_shifts" :key="s.id" class="mega-list-item">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <strong>{{ s.trait_name }}</strong>
                            <span style="color: var(--nv-amber);">{{ s.previous_value.toFixed(2) }} &rarr; {{ s.new_value.toFixed(2) }}</span>
                        </div>
                        <div v-if="s.change_reason" style="color: rgba(255,255,255,0.6); font-size: 0.85em;">{{ s.change_reason }}</div>
                    </div>
                </div>
            </div>

            <!-- PREFERENCES TAB -->
            <div v-else-if="activeTab === 'preferences'">
                <!-- Filters -->
                <div class="mega-filter-row" style="margin-bottom: 16px;">
                    <select v-model="domainFilter" class="mega-select">
                        <option value="">All domains</option>
                        <option v-for="d in ['coding','communication','aesthetic','philosophical','social','general']" :value="d">{{ d }}</option>
                    </select>
                    <select v-model="statusFilter" class="mega-select">
                        <option value="">All statuses</option>
                        <option v-for="s in ['active','evolved','faded','contradicted']" :value="s">{{ s }}</option>
                    </select>
                </div>

                <div v-if="!preferences.length" class="mega-empty">
                    No preferences recorded yet. Use <code>record_preference</code> to capture opinions.
                </div>
                <div v-else class="mega-card-grid">
                    <div v-for="pref in preferences" :key="pref.id"
                         class="mega-card mega-card-hover"
                         :class="{ 'mega-card-selected': selectedPref === pref.id }"
                         @click="selectPref(pref)">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                            <span class="mega-badge" :style="{ background: getDomainColor(pref.domain) + '33', color: getDomainColor(pref.domain) }">
                                {{ pref.domain }}
                            </span>
                            <span class="mega-badge" :class="'sentiment-' + sentimentClass(pref.sentiment)">
                                {{ sentimentLabel(pref.sentiment) }}
                            </span>
                            <span v-if="pref.status !== 'active'" class="mega-badge" style="background: rgba(255,255,255,0.05);">{{ pref.status }}</span>
                        </div>
                        <div style="color: rgba(255,255,255,0.85); font-size: 0.9em;">{{ pref.content }}</div>
                        <div class="mega-bar-track" style="margin-top: 8px;">
                            <div class="mega-bar-fill" :style="{ width: (pref.strength * 100) + '%', background: getDomainColor(pref.domain) }"></div>
                        </div>
                        <div style="font-size: 0.75em; color: rgba(255,255,255,0.4); margin-top: 4px;">
                            Strength: {{ pref.strength.toFixed(2) }}
                        </div>
                    </div>
                </div>

                <!-- Preference detail -->
                <div v-if="selectedPref && prefDetail" class="mega-card" style="margin-top: 24px;">
                    <h3 style="margin-bottom: 12px;">Change History</h3>
                    <div v-if="prefDetail.history && prefDetail.history.length">
                        <div v-for="h in prefDetail.history" :key="h.id" class="mega-list-item">
                            <div style="color: rgba(255,255,255,0.7); font-size: 0.9em;">
                                {{ h.previous_content }}
                            </div>
                            <div style="display: flex; gap: 10px; font-size: 0.8em; color: rgba(255,255,255,0.5); margin-top: 4px;">
                                <span>Strength: {{ h.previous_strength.toFixed(2) }}</span>
                                <span>Status: {{ h.previous_status }}</span>
                            </div>
                            <div v-if="h.change_reason" style="color: rgba(255,255,255,0.5); font-size: 0.8em; font-style: italic;">{{ h.change_reason }}</div>
                            <div style="color: rgba(255,255,255,0.35); font-size: 0.75em; margin-top: 2px;">{{ formatDate(h.created_at) }}</div>
                        </div>
                    </div>
                    <div v-else style="color: rgba(255,255,255,0.5);">No changes recorded yet.</div>
                </div>
            </div>

            <!-- VOICE NOTES TAB -->
            <div v-else-if="activeTab === 'voice'">
                <!-- Filters -->
                <div class="mega-filter-row" style="margin-bottom: 16px;">
                    <select v-model="noteTypeFilter" class="mega-select">
                        <option value="">All types</option>
                        <option v-for="t in ['pattern','phrase','habit','observation','evolution']" :value="t">{{ t }}</option>
                    </select>
                    <select v-model="noteStatusFilter" class="mega-select">
                        <option value="">All statuses</option>
                        <option v-for="s in ['active','retired','evolved']" :value="s">{{ s }}</option>
                    </select>
                </div>

                <div v-if="!voiceNotes.length" class="mega-empty">
                    No voice notes yet. Use <code>note_voice_pattern</code> to record style observations.
                </div>
                <div v-else>
                    <div v-for="note in voiceNotes" :key="note.id" class="mega-card" style="margin-bottom: 12px;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                            <span class="mega-badge" style="background: rgba(167, 139, 250, 0.2); color: #a78bfa;">{{ note.note_type }}</span>
                            <span class="mega-badge" :style="{ background: note.status === 'active' ? 'rgba(52,211,153,0.15)' : 'rgba(255,255,255,0.05)', color: note.status === 'active' ? '#34d399' : 'rgba(255,255,255,0.5)' }">{{ note.status }}</span>
                            <span style="flex: 1;"></span>
                            <span style="font-size: 0.75em; color: rgba(255,255,255,0.35);">{{ formatDate(note.created_at) }}</span>
                        </div>
                        <div style="color: rgba(255,255,255,0.85); font-size: 0.9em;">{{ note.content }}</div>
                        <div v-if="note.source_context" style="color: rgba(255,255,255,0.45); font-size: 0.8em; margin-top: 6px; font-style: italic;">
                            Context: {{ note.source_context }}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `,

    methods: {
        formatDate: App.formatDate,
    },
});
