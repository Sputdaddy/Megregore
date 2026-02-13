/* ============================================================
   Megregore — Memory Browser Page (Vue Component)
   ============================================================ */

megregoreApp.component('memories-page', {
    setup() {
        // State
        const memories = ref([]);
        const total = ref(0);
        const offset = ref(0);
        const limit = ref(20);
        const memoryType = ref('');
        const sortBy = ref('created_at');
        const sortOrder = ref('desc');
        const searchQuery = ref('');
        const expandedId = ref(null);
        const linkedMemories = reactive({});
        const linkedLoading = reactive({});
        const loading = ref(false);
        const error = ref('');

        // Search debounce
        let searchTimeout = null;

        // Computed
        const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1);
        const totalPages = computed(() => Math.ceil(total.value / limit.value));
        const isSearching = computed(() => searchQuery.value.trim().length > 0);

        // Methods
        function resetPagination() {
            offset.value = 0;
        }

        async function loadMemories() {
            loading.value = true;
            error.value = '';
            try {
                let data;
                if (searchQuery.value.trim()) {
                    data = await App.api('/memories/search', {
                        q: searchQuery.value,
                        limit: limit.value,
                        memory_type: memoryType.value || null,
                    });
                    memories.value = data.memories || [];
                    total.value = data.count || memories.value.length;
                } else {
                    data = await App.api('/memories', {
                        limit: limit.value,
                        offset: offset.value,
                        memory_type: memoryType.value || null,
                        sort_by: sortBy.value,
                        sort_order: sortOrder.value,
                    });
                    memories.value = data.memories || [];
                    total.value = data.total || 0;
                }
            } catch (e) {
                error.value = e.message || 'Failed to load memories';
                memories.value = [];
                total.value = 0;
            } finally {
                loading.value = false;
            }
        }

        async function loadLinked(memoryId) {
            if (linkedMemories[memoryId]) return;

            linkedLoading[memoryId] = true;
            try {
                const data = await App.api(`/memories/${memoryId}`);
                linkedMemories[memoryId] = data.linked || [];
            } catch (e) {
                linkedMemories[memoryId] = [];
            } finally {
                linkedLoading[memoryId] = false;
            }
        }

        function toggleExpand(memoryId) {
            if (expandedId.value === memoryId) {
                expandedId.value = null;
            } else {
                expandedId.value = memoryId;
                if (!linkedMemories[memoryId]) {
                    loadLinked(memoryId);
                }
            }
        }

        function handleSearchInput(event) {
            if (searchTimeout) clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                resetPagination();
                loadMemories();
            }, 350);
        }

        function handleSearchKeydown(event) {
            if (event.key === 'Escape') {
                searchQuery.value = '';
                resetPagination();
                loadMemories();
            }
        }

        function onFilterChange() {
            resetPagination();
            loadMemories();
        }

        function prevPage() {
            if (offset.value > 0) {
                offset.value = Math.max(0, offset.value - limit.value);
                loadMemories();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        }

        function nextPage() {
            if (offset.value + limit.value < total.value) {
                offset.value += limit.value;
                loadMemories();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        }

        function shouldTruncate(content) {
            return content && content.length > 200;
        }

        function getDisplayContent(memory) {
            if (!memory.content) return '';
            if (expandedId.value === memory.id || memory.content.length <= 200) {
                return memory.content;
            }
            return App.truncateText(memory.content, 200);
        }

        // Lifecycle
        onMounted(() => {
            loadMemories();
        });

        return {
            memories,
            total,
            offset,
            limit,
            memoryType,
            sortBy,
            sortOrder,
            searchQuery,
            expandedId,
            linkedMemories,
            linkedLoading,
            loading,
            error,
            currentPage,
            totalPages,
            isSearching,
            toggleExpand,
            handleSearchInput,
            handleSearchKeydown,
            onFilterChange,
            prevPage,
            nextPage,
            shouldTruncate,
            getDisplayContent,
        };
    },

    template: `
        <div v-if="loading" class="loading">
            <div class="spinner"></div>
            <p>Loading memories...</p>
        </div>

        <div v-else-if="error" class="empty-state">
            <p>{{ error }}</p>
        </div>

        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Memory Browser</h1>
                <p class="subtitle">Explore and search through your stored memories</p>
            </div>

            <div class="search-bar-wrap">
                <svg class="search-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM18 18l-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <input
                    type="text"
                    class="search-bar"
                    v-model="searchQuery"
                    @input="handleSearchInput"
                    @keydown="handleSearchKeydown"
                    placeholder="Search memories... (press Esc to clear)"
                />
            </div>

            <div class="filter-row">
                <div>
                    <label class="filter-label">Type</label>
                    <select class="filter-select" v-model="memoryType" @change="onFilterChange">
                        <option value="">All Types</option>
                        <option value="experience">Experience</option>
                        <option value="fact">Fact</option>
                        <option value="observation">Observation</option>
                        <option value="reflection">Reflection</option>
                        <option value="insight">Insight</option>
                        <option value="emotion">Emotion</option>
                    </select>
                </div>

                <div>
                    <label class="filter-label">Sort By</label>
                    <select class="filter-select" v-model="sortBy" @change="onFilterChange">
                        <option value="created_at">Date Created</option>
                        <option value="importance">Importance</option>
                        <option value="access_count">Access Count</option>
                        <option value="activation_level">Activation Level</option>
                        <option value="emotional_weight">Emotional Weight</option>
                        <option value="last_accessed">Last Accessed</option>
                    </select>
                </div>

                <div>
                    <label class="filter-label">Order</label>
                    <select class="filter-select" v-model="sortOrder" @change="onFilterChange">
                        <option value="desc">Descending</option>
                        <option value="asc">Ascending</option>
                    </select>
                </div>
            </div>

            <div v-if="memories.length === 0" class="empty-state">
                <p>No memories found</p>
            </div>

            <div v-else>
                <div
                    v-for="memory in memories"
                    :key="memory.id"
                    :class="['card', 'memory-card', { expanded: expandedId === memory.id }]"
                >
                    <div class="card-header">
                        <div>
                            <span v-html="typeBadgeHtml(memory.memory_type)"></span>
                            <span v-html="emotionalIndicatorHtml(memory.emotional_weight)"></span>
                        </div>
                        <div v-html="importanceDotsHtml(memory.importance)"></div>
                    </div>

                    <div class="card-content">
                        <div :class="{ truncated: expandedId !== memory.id && shouldTruncate(memory.content) }">
                            {{ getDisplayContent(memory) }}
                        </div>
                        <button
                            v-if="shouldTruncate(memory.content)"
                            class="expand-btn"
                            @click="toggleExpand(memory.id)"
                        >
                            {{ expandedId === memory.id ? 'Show less' : 'Show more' }}
                        </button>
                    </div>

                    <div class="card-meta">
                        <div class="card-meta-item" v-if="memory.tags && memory.tags.length > 0">
                            <span v-html="tagPillsHtml(memory.tags)"></span>
                        </div>
                        <div class="card-meta-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/>
                                <polyline points="12 6 12 12 16 14"/>
                            </svg>
                            {{ formatDate(memory.created_at) }}
                        </div>
                        <div class="card-meta-item">
                            Accessed {{ memory.access_count }}x
                        </div>
                        <div class="card-meta-item">
                            <span v-html="activationBarHtml(memory.activation_level)"></span>
                        </div>
                        <div v-if="memory.thread_id" class="card-meta-item">
                            <span class="thread-badge">Thread #{{ memory.thread_id }}</span>
                        </div>
                    </div>

                    <div v-if="expandedId === memory.id" class="memory-detail">
                        <div class="linked-label">Linked Memories</div>

                        <div v-if="linkedLoading[memory.id]" class="loading">
                            <div class="spinner"></div>
                        </div>

                        <div v-else-if="!linkedMemories[memory.id] || linkedMemories[memory.id].length === 0" class="empty-state">
                            <p>No linked memories</p>
                        </div>

                        <div v-else>
                            <div
                                v-for="linked in linkedMemories[memory.id]"
                                :key="linked.id"
                                class="card linked-memory"
                            >
                                <div class="card-header">
                                    <span v-html="typeBadgeHtml(linked.memory_type)"></span>
                                    <span class="link-type-label">{{ linked.link_type }}</span>
                                </div>
                                <div class="card-content">
                                    {{ linked.content && linked.content.length > 200 ? linked.content.substring(0, 200) + '...' : linked.content }}
                                </div>
                                <div v-html="importanceBarHtml(linked.importance)"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="!isSearching && total > limit" class="pagination">
                <button
                    class="pagination-btn"
                    @click="prevPage"
                    :disabled="offset === 0"
                >
                    Previous
                </button>
                <span class="pagination-info">
                    Page {{ currentPage }} of {{ totalPages }} ({{ total }} total)
                </span>
                <button
                    class="pagination-btn"
                    @click="nextPage"
                    :disabled="offset + limit >= total"
                >
                    Next
                </button>
            </div>

            <div v-else-if="isSearching" class="pagination-info" style="text-align: center; margin-top: 2rem;">
                Found {{ total }} {{ total === 1 ? 'result' : 'results' }}
            </div>
        </div>
    `,

    methods: {
        formatDate: App.formatDate,
        truncate: App.truncateText,
        typeBadgeHtml: App.typeBadge,
        emotionalIndicatorHtml: App.emotionalIndicator,
        importanceDotsHtml: App.importanceDots,
        importanceBarHtml: App.importanceBar,
        activationBarHtml: App.activationBar,
        tagPillsHtml: App.tagPills,
    },
});
