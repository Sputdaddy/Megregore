/* ============================================================
   Megregore — Sessions Page (Vue Component)
   Lists sessions with expandable cards showing mood and memories
   ============================================================ */

megregoreApp.component('sessions-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const sessions = ref([]);
        const expandedId = ref(null);
        const sessionMoods = reactive({});
        const sessionMemories = reactive({});
        const sessionLoading = reactive({});

        async function loadSessions() {
            loading.value = true;
            error.value = '';
            try {
                const result = await App.api('/sessions', { limit: 50 });
                sessions.value = result.sessions || [];
            } catch (err) {
                error.value = err.message;
                sessions.value = [];
            } finally {
                loading.value = false;
            }
        }

        async function toggleExpanded(sessionId) {
            if (expandedId.value === sessionId) {
                expandedId.value = null;
                return;
            }

            expandedId.value = sessionId;

            // Load mood and memories if not already cached
            if (!sessionMoods[sessionId]) {
                sessionLoading[sessionId] = true;
                try {
                    const [moodData, memoriesData] = await Promise.all([
                        App.api(`/sessions/${sessionId}`),
                        App.api(`/sessions/${sessionId}/memories`, { limit: 20 }),
                    ]);
                    sessionMoods[sessionId] = moodData;
                    sessionMemories[sessionId] = memoriesData.memories || [];
                } catch (err) {
                    console.error(`Error loading session ${sessionId}:`, err);
                    sessionMoods[sessionId] = {};
                    sessionMemories[sessionId] = [];
                } finally {
                    sessionLoading[sessionId] = false;
                }
            }
        }

        const moodDotColor = (sessionId) => {
            const data = sessionMoods[sessionId];
            if (!data) return 'neutral';
            const mood = data.mood || {};
            const emotion = mood.avg_emotion || 0;
            if (emotion > 0.05) return 'positive';
            if (emotion < -0.05) return 'negative';
            return 'neutral';
        };

        onMounted(() => {
            loadSessions();
        });

        return {
            loading,
            error,
            sessions,
            expandedId,
            sessionLoading,
            sessionMoods,
            sessionMemories,
            toggleExpanded,
            moodDotColor,
        };
    },

    template: `
        <div v-if="loading" class="loading"><div class="spinner"></div></div>

        <div v-else-if="error" class="empty-state fade-in">
            <div class="empty-glyph">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/>
                </svg>
            </div>
            <h3>Could not load sessions</h3>
            <p>{{ error }}</p>
        </div>

        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Sessions</h1>
                <p>Conversation sessions and their memory traces</p>
            </div>

            <div v-if="sessions.length" class="sessions-list">
                <div
                    v-for="session in sessions"
                    :key="session.id"
                    class="session-card"
                    :class="{ expanded: expandedId === session.id }"
                    @click="toggleExpanded(session.id)"
                >
                    <!-- Session Header -->
                    <div class="session-card-header">
                        <div class="session-header-left">
                            <div class="session-id-badge">{{ session.id }}</div>
                            <span class="session-summary">{{ session.summary || 'No summary' }}</span>
                        </div>
                        <div class="session-header-right">
                            <span class="memory-count muted text-sm">{{ session.memory_count || 0 }} memories</span>
                            <span class="session-date muted text-sm">{{ formatDate(session.created_at) }}</span>
                        </div>
                    </div>

                    <!-- Expanded Content -->
                    <div v-if="expandedId === session.id" class="session-card-content">
                        <!-- Loading State -->
                        <div v-if="sessionLoading[session.id]" class="loading" style="margin-bottom:20px;">
                            <div class="spinner" style="width:24px;height:24px;"></div>
                        </div>

                        <!-- Mood Summary -->
                        <div v-else-if="sessionMoods[session.id]" class="session-mood-section">
                            <div class="mood-header">
                                <span class="mood-label">Emotional Tone</span>
                                <span v-html="emotionalIndicator((sessionMoods[session.id].mood || {}).avg_emotion || 0)" class="mood-indicator"></span>
                            </div>
                            <div v-if="sessionMoods[session.id].mood && sessionMoods[session.id].mood.summary" class="mood-summary text-sm muted">
                                {{ sessionMoods[session.id].mood.summary }}
                            </div>
                            <div class="session-dates text-sm muted" style="margin-top:10px;">
                                <div>Started: {{ formatDateFull(session.created_at) }}</div>
                                <div v-if="session.updated_at">Ended: {{ formatDateFull(session.updated_at) }}</div>
                            </div>
                        </div>

                        <!-- Memories List -->
                        <div v-if="sessionMemories[session.id] && sessionMemories[session.id].length" class="session-memories">
                            <div class="section-title" style="margin-top:20px;">
                                Memories
                                <span class="count">{{ sessionMemories[session.id].length }}</span>
                            </div>
                            <div class="memories-list">
                                <div
                                    v-for="memory in sessionMemories[session.id]"
                                    :key="memory.id"
                                    class="memory-item"
                                >
                                    <div class="memory-header">
                                        <span v-html="typeBadge(memory.memory_type)" class="memory-badge"></span>
                                        <span v-html="importanceBar(memory.importance)" class="memory-importance"></span>
                                    </div>
                                    <div class="memory-content text-sm">{{ truncateText(memory.content, 200) }}</div>
                                    <div class="memory-meta">
                                        <span v-if="memory.tags && memory.tags.length" v-html="tagPills(memory.tags)"></span>
                                        <span class="memory-emotional" v-html="emotionalIndicator(memory.emotional_weight)"></span>
                                        <span class="memory-date muted text-sm">{{ formatDate(memory.created_at) }}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div v-else-if="!sessionLoading[session.id]" class="empty-state" style="padding:20px 10px;">
                            <p class="muted text-sm">No memories in this session.</p>
                        </div>
                    </div>
                </div>
            </div>

            <div v-else class="empty-state fade-in">
                <div class="empty-glyph">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                </div>
                <h3>No sessions yet</h3>
                <p>Sessions will appear here as memories are recorded.</p>
            </div>
        </div>
    `,

    methods: {
        formatDate: App.formatDate,
        formatDateFull: App.formatDateFull,
        truncateText: App.truncateText,
        typeBadge: App.typeBadge,
        importanceBar: App.importanceBar,
        emotionalIndicator: App.emotionalIndicator,
        tagPills: App.tagPills,
    },
});
