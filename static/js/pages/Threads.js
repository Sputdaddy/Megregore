/* ============================================================
   Megregore — Threads Page (Vue Component)
   Displays memory threads with expandable details and lazy-loaded memories
   ============================================================ */

megregoreApp.component('threads-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const threads = ref([]);
        const expandedId = ref(null);
        const loadingMemories = ref(null);
        const memoriesCache = reactive({});

        async function loadThreads() {
            loading.value = true;
            error.value = '';
            try {
                const data = await App.api('/threads', { limit: 50 });
                threads.value = data.threads || [];
            } catch (err) {
                error.value = err.message;
                threads.value = [];
            } finally {
                loading.value = false;
            }
        }

        async function loadThreadMemories(threadId) {
            if (memoriesCache[threadId]) {
                expandedId.value = threadId;
                return;
            }

            loadingMemories.value = threadId;
            try {
                const data = await App.api(`/threads/${threadId}/memories`, { limit: 100 });
                memoriesCache[threadId] = data.memories || [];
                expandedId.value = threadId;
            } catch (err) {
                console.error(`Failed to load memories for thread ${threadId}:`, err);
            } finally {
                loadingMemories.value = null;
            }
        }

        function toggleExpand(threadId) {
            if (expandedId.value === threadId) {
                expandedId.value = null;
            } else {
                loadThreadMemories(threadId);
            }
        }

        const currentMemories = computed(() => {
            return expandedId.value ? (memoriesCache[expandedId.value] || []) : [];
        });

        onMounted(() => {
            loadThreads();
        });

        return {
            loading,
            error,
            threads,
            expandedId,
            loadingMemories,
            currentMemories,
            toggleExpand,
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
            <h3>Could not load threads</h3>
            <p>{{ error }}</p>
        </div>

        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Threads</h1>
                <p>Semantic topic groupings that persist across sessions</p>
            </div>

            <div v-if="threads.length" class="threads-list">
                <div
                    v-for="thread in threads"
                    :key="thread.id"
                    class="thread-card"
                    :class="{ expanded: expandedId === thread.id }"
                >
                    <div class="thread-header" @click="toggleExpand(thread.id)">
                        <div class="thread-title-section">
                            <h3 class="thread-title">{{ thread.title }}</h3>
                            <p v-if="thread.description" class="thread-description">{{ thread.description }}</p>
                        </div>
                        <div class="thread-meta">
                            <span class="thread-count">{{ thread.memory_count }} memories</span>
                            <svg class="thread-toggle-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                        </div>
                    </div>

                    <div v-if="expandedId === thread.id" class="thread-details">
                        <div v-if="loadingMemories === thread.id" class="loading" style="padding:20px;">
                            <div class="spinner"></div>
                        </div>
                        <div v-else-if="currentMemories.length" class="thread-memories">
                            <div
                                v-for="memory in currentMemories"
                                :key="memory.id"
                                class="memory-item"
                            >
                                <div class="memory-header" v-html="typeBadgeHtml(memory.memory_type) + importanceBarHtml(memory.importance) + activationBarHtml(memory.activation_level)"></div>
                                <div class="memory-content text-sm">{{ truncate(memory.content, 250) }}</div>
                                <div class="memory-meta">
                                    <span v-if="memory.tags && memory.tags.length" v-html="tagPillsHtml(memory.tags)"></span>
                                    <span class="memory-date muted text-sm">{{ formatDate(memory.created_at) }}</span>
                                </div>
                            </div>
                        </div>
                        <div v-else class="empty-state" style="padding:20px 10px;">
                            <p class="muted text-sm">No memories in this thread.</p>
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
                <h3>No threads yet</h3>
                <p>Threads will appear as memories are created and linked.</p>
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
