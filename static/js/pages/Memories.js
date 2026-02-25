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
        const editingId = ref(null);
        const editForm = reactive({ content: '', importance: 5, tags: '', emotional_weight: 0 });
        const deleteConfirmId = ref(null);

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
                    const params = {
                        limit: limit.value,
                        offset: offset.value,
                        sort_by: sortBy.value,
                        sort_order: sortOrder.value,
                    };
                    if (memoryType.value === 'permanent') {
                        params.permanent = true;
                    } else if (memoryType.value) {
                        params.memory_type = memoryType.value;
                    }
                    data = await App.api('/memories', params);
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

        function startEdit(memory) {
            editingId.value = memory.id;
            editForm.content = memory.content || '';
            editForm.importance = memory.importance || 5;
            editForm.tags = (memory.tags || []).join(', ');
            editForm.emotional_weight = memory.emotional_weight || 0;
        }

        function cancelEdit() {
            editingId.value = null;
        }

        async function saveEdit(memoryId) {
            try {
                const updates = {};
                if (editForm.content) updates.content = editForm.content;
                updates.importance = editForm.importance;
                if (editForm.tags.trim()) {
                    updates.tags = editForm.tags.split(',').map(t => t.trim()).filter(Boolean);
                }
                updates.emotional_weight = parseFloat(editForm.emotional_weight) || 0;
                await App.apiPut(`/memories/${memoryId}`, updates);
                editingId.value = null;
                await loadMemories();
            } catch (e) {
                error.value = 'Failed to save: ' + (e.message || 'Unknown error');
            }
        }

        async function togglePin(memory) {
            try {
                const endpoint = memory.is_permanent
                    ? `/memories/${memory.id}/unpin`
                    : `/memories/${memory.id}/pin`;
                await App.apiPost(endpoint);
                await loadMemories();
            } catch (e) {
                error.value = 'Failed to toggle pin: ' + (e.message || 'Unknown error');
            }
        }

        async function deleteMemory(memoryId) {
            if (!window.confirm('Are you sure you want to permanently delete this memory? This cannot be undone.')) {
                return;
            }
            try {
                await App.apiDelete(`/memories/${memoryId}`);
                await loadMemories();
            } catch (e) {
                error.value = 'Failed to delete: ' + (e.message || 'Unknown error');
            }
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
            editingId,
            editForm,
            deleteConfirmId,
            startEdit,
            cancelEdit,
            saveEdit,
            deleteMemory,
            togglePin,
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
                        <option value="permanent">Pinned Only</option>
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
                            <span v-if="memory.is_permanent" style="display: inline-block; font-size: 0.65rem; padding: 2px 8px; border-radius: 10px; background: rgba(251,191,36,0.15); color: #fbbf24; border: 1px solid rgba(251,191,36,0.25); margin-left: 6px; font-weight: 600; letter-spacing: 0.04em;">PINNED</span>
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

                    <!-- Action Buttons -->
                    <div style="display: flex; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.04);">
                        <button @click="togglePin(memory)"
                                :style="memory.is_permanent
                                    ? 'font-size: 0.75rem; padding: 4px 12px; border-radius: 4px; background: rgba(251,191,36,0.1); color: #fbbf24; border: 1px solid rgba(251,191,36,0.2); cursor: pointer; transition: all 0.2s;'
                                    : 'font-size: 0.75rem; padding: 4px 12px; border-radius: 4px; background: rgba(255,255,255,0.05); color: #8a8690; border: 1px solid rgba(255,255,255,0.08); cursor: pointer; transition: all 0.2s;'">
                            {{ memory.is_permanent ? 'Unpin' : 'Pin' }}
                        </button>
                        <button @click="startEdit(memory)"
                                style="font-size: 0.75rem; padding: 4px 12px; border-radius: 4px; background: rgba(212,160,83,0.1); color: #d4a053; border: 1px solid rgba(212,160,83,0.2); cursor: pointer; transition: all 0.2s;"
                                v-if="editingId !== memory.id">
                            Edit
                        </button>
                        <button @click="deleteMemory(memory.id)"
                                style="font-size: 0.75rem; padding: 4px 12px; border-radius: 4px; background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.2); cursor: pointer; transition: all 0.2s;">
                            Delete
                        </button>
                    </div>

                    <!-- Inline Edit Form -->
                    <div v-if="editingId === memory.id" style="margin-top: 12px; padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
                        <div style="margin-bottom: 10px;">
                            <label style="display: block; font-size: 0.7rem; color: var(--text-muted, #8a8690); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px;">Content</label>
                            <textarea v-model="editForm.content"
                                      style="width: 100%; min-height: 80px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; color: inherit; padding: 8px; font-family: inherit; font-size: 0.85rem; resize: vertical;"></textarea>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 12px;">
                            <div>
                                <label style="display: block; font-size: 0.7rem; color: var(--text-muted, #8a8690); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px;">Importance (1-10)</label>
                                <input type="number" v-model.number="editForm.importance" min="1" max="10"
                                       style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; color: inherit; padding: 6px 8px; font-size: 0.85rem;">
                            </div>
                            <div>
                                <label style="display: block; font-size: 0.7rem; color: var(--text-muted, #8a8690); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px;">Tags (comma-sep)</label>
                                <input type="text" v-model="editForm.tags"
                                       style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; color: inherit; padding: 6px 8px; font-size: 0.85rem;">
                            </div>
                            <div>
                                <label style="display: block; font-size: 0.7rem; color: var(--text-muted, #8a8690); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px;">Emotion (-1 to 1)</label>
                                <input type="number" v-model.number="editForm.emotional_weight" min="-1" max="1" step="0.1"
                                       style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; color: inherit; padding: 6px 8px; font-size: 0.85rem;">
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px;">
                            <button @click="saveEdit(memory.id)"
                                    style="font-size: 0.75rem; padding: 6px 16px; border-radius: 4px; background: rgba(79,209,197,0.15); color: #4fd1c5; border: 1px solid rgba(79,209,197,0.3); cursor: pointer;">
                                Save
                            </button>
                            <button @click="cancelEdit()"
                                    style="font-size: 0.75rem; padding: 6px 16px; border-radius: 4px; background: rgba(255,255,255,0.05); color: #8a8690; border: 1px solid rgba(255,255,255,0.08); cursor: pointer;">
                                Cancel
                            </button>
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
