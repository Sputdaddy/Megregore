/* ============================================================
   Megregore — Identity Page (Vue Component)
   Shows current identity document and version history timeline
   ============================================================ */

megregoreApp.component('identity-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const identity = ref(null);
        const history = ref([]);
        const expandedIndex = ref(null);

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                [identity.value, history.value] = await Promise.all([
                    App.api('/identity'),
                    App.api('/identity/history'),
                ]);
            } catch (err) {
                error.value = err.message;
                identity.value = null;
                history.value = [];
            } finally {
                loading.value = false;
            }
        }

        function toggleExpanded(index) {
            expandedIndex.value = expandedIndex.value === index ? null : index;
        }

        const identityContent = computed(() => {
            return identity.value?.content || '';
        });

        const identityVersion = computed(() => {
            return identity.value?.version || 0;
        });

        const identityUpdatedAt = computed(() => {
            return identity.value?.updated_at || '';
        });

        const historyItems = computed(() => {
            return history.value?.history || [];
        });

        onMounted(() => {
            loadData();
        });

        return {
            loading,
            error,
            identityContent,
            identityVersion,
            identityUpdatedAt,
            historyItems,
            expandedIndex,
            toggleExpanded,
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
            <h3>Could not load identity</h3>
            <p>{{ error }}</p>
        </div>

        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Identity</h1>
                <p>Echo's self-understanding, shaped by memories and reflections</p>
            </div>

            <!-- Current Identity Document -->
            <div class="section">
                <div class="section-title">
                    Current Identity
                    <span class="count" v-html="versionBadge()"></span>
                </div>
                <div class="card identity-document">
                    <div v-if="identityContent" class="markdown-content" v-html="renderMarkdown(identityContent)"></div>
                    <div v-else class="empty-state" style="padding:30px 10px;">
                        <p class="muted text-sm">No identity document yet.</p>
                    </div>
                    <div v-if="identityUpdatedAt" class="card-meta" style="margin-top:20px;padding-top:20px;border-top:1px solid var(--border-color);">
                        <span class="muted text-sm">Updated {{ formatDateFull(identityUpdatedAt) }}</span>
                    </div>
                </div>
            </div>

            <!-- Version History Timeline -->
            <div v-if="historyItems.length" class="section">
                <div class="section-title">
                    Version History
                    <span class="count">{{ historyItems.length }}</span>
                </div>
                <div class="history-timeline">
                    <div
                        v-for="(item, index) in historyItems"
                        :key="index"
                        class="history-card"
                        :class="{ expanded: expandedIndex === index }"
                        @click="toggleExpanded(index)"
                    >
                        <div class="history-card-header">
                            <div class="history-version-info">
                                <span v-html="versionBadgeWithNumber(item.version)" class="history-badge"></span>
                                <span class="history-reason">{{ item.updated_reason || 'No reason provided' }}</span>
                            </div>
                            <span class="history-date muted text-sm">{{ formatDate(item.updated_at) }}</span>
                        </div>
                        <div v-if="expandedIndex === index" class="history-card-content">
                            <div class="markdown-content" v-html="renderMarkdown(item.content)"></div>
                            <div v-if="item.updated_at" class="card-meta" style="margin-top:15px;padding-top:15px;border-top:1px solid var(--border-color);">
                                <span class="muted text-sm">{{ formatDateFull(item.updated_at) }}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `,

    methods: {
        formatDate: App.formatDate,
        formatDateFull: App.formatDateFull,
        renderMarkdown: App.renderMarkdown,
        versionBadge() {
            return `<span class="version-badge">v${this.identityVersion}</span>`;
        },
        versionBadgeWithNumber(version) {
            return `<span class="version-badge">v${version || 0}</span>`;
        },
    },
});
