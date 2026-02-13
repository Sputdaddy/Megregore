/* ============================================================
   Megregore — Reflections Page (Vue Component)
   Displays reflections with filterable insight types and pagination
   ============================================================ */

megregoreApp.component('reflections-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const reflections = ref([]);
        const total = ref(0);
        const offset = ref(0);
        const limit = 30;
        const insightType = ref('');

        const insightTypes = ['pattern', 'growth', 'connection', 'realization'];

        async function loadReflections() {
            loading.value = true;
            error.value = '';
            try {
                const params = {
                    limit,
                    offset: offset.value,
                };
                if (insightType.value) {
                    params.insight_type = insightType.value;
                }
                const data = await App.api('/reflections', params);
                reflections.value = data.reflections || [];
                total.value = data.total || 0;
            } catch (err) {
                error.value = err.message;
                reflections.value = [];
                total.value = 0;
            } finally {
                loading.value = false;
            }
        }

        function setInsightType(type) {
            if (insightType.value === type) {
                insightType.value = '';
            } else {
                insightType.value = type;
            }
            offset.value = 0;
            loadReflections();
        }

        function previousPage() {
            offset.value = Math.max(0, offset.value - limit);
            loadReflections();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function nextPage() {
            offset.value += limit;
            loadReflections();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        const currentPage = computed(() => {
            return Math.floor(offset.value / limit) + 1;
        });

        const totalPages = computed(() => {
            return Math.ceil(total.value / limit);
        });

        const canGoPrevious = computed(() => {
            return offset.value > 0;
        });

        const canGoNext = computed(() => {
            return offset.value + limit < total.value;
        });

        onMounted(() => {
            loadReflections();
        });

        return {
            loading,
            error,
            reflections,
            total,
            insightType,
            insightTypes,
            currentPage,
            totalPages,
            canGoPrevious,
            canGoNext,
            setInsightType,
            previousPage,
            nextPage,
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
            <h3>Could not load reflections</h3>
            <p>{{ error }}</p>
        </div>

        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Reflections</h1>
                <p>Insights synthesized from patterns across memories</p>
            </div>

            <!-- Filter Chips -->
            <div class="filter-chips">
                <button
                    class="filter-chip"
                    :class="{ active: insightType === '' }"
                    @click="setInsightType('')"
                >
                    All
                </button>
                <button
                    v-for="type in insightTypes"
                    :key="type"
                    class="filter-chip"
                    :class="{ active: insightType === type }"
                    @click="setInsightType(type)"
                >
                    {{ type }}
                </button>
            </div>

            <!-- Reflections Timeline -->
            <div v-if="reflections.length" class="reflections-timeline">
                <div
                    v-for="reflection in reflections"
                    :key="reflection.id"
                    class="reflection-card"
                >
                    <div class="reflection-header">
                        <span v-html="insightBadgeHtml(reflection.insight_type)" class="reflection-badge"></span>
                        <span class="reflection-date muted text-sm">{{ formatDate(reflection.created_at) }}</span>
                    </div>
                    <div class="reflection-content">{{ reflection.content }}</div>
                    <div class="reflection-meta">
                        <div v-if="reflection.memory_ids && reflection.memory_ids.length" class="reflection-memories">
                            <span class="muted text-xs">Memory IDs:</span>
                            <span class="memory-ids">{{ reflection.memory_ids.join(', ') }}</span>
                        </div>
                        <div v-if="reflection.session_id" class="reflection-session">
                            <span class="muted text-xs">Session:</span>
                            <span class="session-id">{{ reflection.session_id }}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div v-else class="empty-state fade-in">
                <div class="empty-glyph">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/>
                    </svg>
                </div>
                <h3>No reflections yet</h3>
                <p v-if="insightType">Try a different filter or check back soon.</p>
                <p v-else>Reflections will appear as memories are consolidated and patterns are discovered.</p>
            </div>

            <!-- Pagination -->
            <div v-if="total > limit" class="pagination">
                <button
                    :disabled="!canGoPrevious"
                    class="btn btn-secondary"
                    @click="previousPage"
                >
                    Previous
                </button>
                <span class="pagination-info">
                    Page {{ currentPage }} of {{ totalPages }}
                </span>
                <button
                    :disabled="!canGoNext"
                    class="btn btn-secondary"
                    @click="nextPage"
                >
                    Next
                </button>
            </div>
        </div>
    `,

    methods: {
        formatDate: App.formatDate,
        insightBadgeHtml: App.insightBadge,
    },
});
