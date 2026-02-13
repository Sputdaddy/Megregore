/* ============================================================
   Megregore — Vue 3 App Bootstrap
   Router, API client, auth state, theme, shared utilities.
   ============================================================ */

const { createApp, ref, reactive, computed, watch, provide, inject,
        onMounted, onUnmounted, nextTick, toRaw } = Vue;

// --- Shared Utilities (available globally as App.*) ---

const App = (() => {

    const API_BASE = '/api';
    const THEME_KEY = 'megregore-theme';
    const PAGES = [
        'dashboard', 'memories', 'identity', 'reflections',
        'sessions', 'graph', 'threads', 'health', 'analytics',
        'growth', 'blind-spots', 'self-model',
    ];

    // --- CSRF Token ---
    // Read from the non-HttpOnly csrf cookie (set by server on login)
    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)megregore_csrf=([^;]+)/);
        return match ? match[1] : '';
    }

    // --- API Client ---
    // Auth is handled via HttpOnly cookies — no token in JS.
    // CSRF token is sent as header on mutating requests.

    async function api(path, params = {}) {
        const url = new URL(API_BASE + path, window.location.origin);
        for (const [k, v] of Object.entries(params)) {
            if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v);
        }
        const res = await fetch(url.toString(), { credentials: 'same-origin' });
        if (res.status === 401) {
            if (window._megregoreApp) window._megregoreApp.logout();
            throw new Error('Authentication required');
        }
        if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
        return res.json();
    }

    async function apiPost(path, body = {}) {
        const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() };
        const res = await fetch(API_BASE + path, {
            method: 'POST', headers, body: JSON.stringify(body), credentials: 'same-origin',
        });
        if (res.status === 401) {
            if (window._megregoreApp) window._megregoreApp.logout();
            throw new Error('Authentication required');
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `API error: ${res.status}`);
        }
        return res.json();
    }

    async function apiPut(path, body = {}) {
        const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() };
        const res = await fetch(API_BASE + path, {
            method: 'PUT', headers, body: JSON.stringify(body), credentials: 'same-origin',
        });
        if (res.status === 401) {
            if (window._megregoreApp) window._megregoreApp.logout();
            throw new Error('Authentication required');
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `API error: ${res.status}`);
        }
        return res.json();
    }

    async function apiDelete(path) {
        const headers = { 'X-CSRF-Token': getCsrfToken() };
        const res = await fetch(API_BASE + path, {
            method: 'DELETE', headers, credentials: 'same-origin',
        });
        if (res.status === 401) {
            if (window._megregoreApp) window._megregoreApp.logout();
            throw new Error('Authentication required');
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `API error: ${res.status}`);
        }
        return res.json();
    }

    // --- Date Formatting ---
    function formatDate(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHr = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHr / 24);
        if (diffSec < 60) return 'just now';
        if (diffMin < 60) return `${diffMin}m ago`;
        if (diffHr < 24) return `${diffHr}h ago`;
        if (diffDay < 7) return `${diffDay}d ago`;
        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const m = months[date.getMonth()], d = date.getDate(), y = date.getFullYear();
        return y === now.getFullYear() ? `${m} ${d}` : `${m} ${d}, ${y}`;
    }

    function formatDateFull(isoString) {
        if (!isoString) return '';
        return new Date(isoString).toLocaleDateString('en-US', {
            year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
        });
    }

    // --- Text ---
    function truncateText(text, maxLen = 200) {
        if (!text || text.length <= maxLen) return text || '';
        return text.substring(0, maxLen).trimEnd() + '...';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // --- Markdown-lite ---
    function renderMarkdown(text) {
        if (!text) return '';
        let html = escapeHtml(text);
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        html = html.replace(/`(.+?)`/g, '<code>$1</code>');
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
        html = html.split('\n\n').map(block => {
            block = block.trim();
            if (!block) return '';
            if (block.startsWith('<h') || block.startsWith('<ul') || block.startsWith('<ol') || block.startsWith('<')) return block;
            return `<p>${block}</p>`;
        }).join('\n');
        html = html.replace(/(?<!\n)\n(?!\n)/g, '<br>');
        return html;
    }

    // --- Legacy Page Support ---
    // During migration, old page renderers can register here
    const _legacyRenderers = {};
    function registerPage(name, renderer) {
        _legacyRenderers[name] = renderer;
    }
    function getLegacyRenderer(name) {
        return _legacyRenderers[name];
    }

    return {
        PAGES, THEME_KEY,
        api, apiPost, apiPut, apiDelete,
        getCsrfToken,
        formatDate, formatDateFull, truncateText, escapeHtml,
        renderMarkdown,
        registerPage, getLegacyRenderer,
        // Legacy compatibility — these are used by old page JS files
        typeBadge(t) { t = (t||'experience').toLowerCase(); return `<span class="type-badge ${t}">${escapeHtml(t)}</span>`; },
        insightBadge(t) { t = (t||'pattern').toLowerCase(); return `<span class="insight-badge ${t}">${escapeHtml(t)}</span>`; },
        importanceDots(v) { v = Math.max(1,Math.min(10,v||5)); let d=''; for(let i=1;i<=10;i++) d+=`<span class="dot ${i<=v?'filled':''}"></span>`; return `<span class="importance-dots" title="Importance: ${v}/10">${d}</span>`; },
        importanceBar(v) { v = Math.max(1,Math.min(10,v||5)); return `<span class="importance-bar"><span class="importance-bar-track"><span class="importance-bar-fill" style="width:${v*10}%"></span></span><span>${v}</span></span>`; },
        emotionalIndicator(w) { w=w||0; let c,l; if(w>0.05){c='positive';l='+'+w.toFixed(2);}else if(w<-0.05){c='negative';l=w.toFixed(2);}else{c='neutral';l='0.00';} return `<span class="emotional-indicator ${c}"><span class="emotional-dot ${c}"></span>${l}</span>`; },
        activationBar(v) { v=Math.max(0,Math.min(1,v||0)); const p=Math.round(v*100); let c='high'; if(v<0.3)c='low'; else if(v<0.7)c='mid'; return `<span class="activation-bar" title="Activation: ${v.toFixed(2)}"><span class="activation-bar-track"><span class="activation-bar-fill ${c}" style="width:${p}%"></span></span><span class="activation-label">${v.toFixed(2)}</span></span>`; },
        tagPills(tags) { if(!tags||!tags.length)return''; return `<span class="tag-pills">${tags.map(t=>`<span class="tag-pill">${escapeHtml(t)}</span>`).join('')}</span>`; },
        emptyState(title, msg) { return `<div class="empty-state fade-in"><div class="empty-glyph"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/></svg></div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(msg)}</p></div>`; },
        loading() { return '<div class="loading"><div class="spinner"></div></div>'; },
        navigate(page) { window.location.hash = '#' + page; },
    };
})();


// --- Vue Root App ---

const megregoreApp = createApp({
    setup() {
        const currentPage = ref('dashboard');
        const isAuthenticated = ref(false);
        const needsSetup = ref(false);
        const loading = ref(true);
        const theme = ref(localStorage.getItem(App.THEME_KEY) || 'dark');
        const pageError = ref(null);

        // Error boundary — catch component crashes inside keep-alive
        Vue.onErrorCaptured((err, instance, info) => {
            const page = currentPage.value;
            console.error(`[Megregore] Component error on "${page}" page:`, err, '\nInfo:', info);
            pageError.value = { page, message: err.message || String(err), info };
            return false; // prevent propagation
        });

        // Apply theme
        function applyTheme() {
            document.documentElement.setAttribute('data-theme', theme.value);
            localStorage.setItem(App.THEME_KEY, theme.value);
        }
        function toggleTheme() {
            theme.value = theme.value === 'dark' ? 'light' : 'dark';
            applyTheme();
        }
        applyTheme();

        // Router
        function getPageFromHash() {
            const hash = window.location.hash.replace('#', '') || 'dashboard';
            const page = App.PAGES.includes(hash) ? hash : 'dashboard';
            console.debug('[Megregore] getPageFromHash:', hash, '->', page);
            return page;
        }

        function navigateTo(page) {
            if (!App.PAGES.includes(page)) page = 'dashboard';
            console.debug('[Megregore] navigateTo:', page);
            pageError.value = null; // clear any previous error on navigation
            window.location.hash = '#' + page;
        }

        // Auth — cookie-based, no token in JS
        async function checkAuth() {
            try {
                const statusRes = await fetch('/api/auth/status');
                const status = await statusRes.json();
                if (!status.setup_complete) {
                    needsSetup.value = true;
                    loading.value = false;
                    return;
                }
                // Cookie is sent automatically — just verify
                const verifyRes = await fetch('/api/auth/verify', {
                    credentials: 'same-origin',
                });
                const verify = await verifyRes.json();
                if (verify.authenticated) {
                    isAuthenticated.value = true;
                }
                loading.value = false;
            } catch (err) {
                console.error('Auth check failed:', err);
                loading.value = false;
            }
        }

        function onLogin() {
            // Cookie is already set by the server — just update state
            isAuthenticated.value = true;
            needsSetup.value = false;
        }

        async function logout() {
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'X-CSRF-Token': App.getCsrfToken() },
                });
            } catch (e) {
                // Best-effort — clear client state regardless
            }
            isAuthenticated.value = false;
        }

        // Expose logout for API client
        window._megregoreApp = { logout };

        // Hash-based routing
        onMounted(() => {
            currentPage.value = getPageFromHash();
            window.addEventListener('hashchange', () => {
                pageError.value = null; // clear error on hash navigation
                const newPage = getPageFromHash();
                console.debug('[Megregore] hashchange -> page:', newPage);
                currentPage.value = newPage;
            });
            checkAuth();
        });

        // Provide to children
        provide('api', App.api);
        provide('theme', { theme, toggleTheme });
        provide('auth', { isAuthenticated, logout });
        provide('navigate', navigateTo);

        return {
            currentPage, isAuthenticated, needsSetup, loading,
            theme, toggleTheme, navigateTo, onLogin, logout,
            pageError,
        };
    },

    template: `
        <div v-if="loading" class="login-overlay">
            <div class="loading"><div class="spinner"></div></div>
        </div>

        <setup-page v-else-if="needsSetup" @setup-complete="needsSetup = false" />

        <login-page v-else-if="!isAuthenticated" @login="onLogin" />

        <template v-else>
            <nav class="sidebar" id="sidebar">
                <div class="sidebar-header">
                    <div class="logo">
                        <div class="logo-glyph" aria-hidden="true"></div>
                        <span class="logo-text">Megregore</span>
                    </div>
                    <p class="logo-sub">Echo's Memory System</p>
                </div>
                <ul class="nav-list">
                    <li v-for="page in pages" :key="page.id">
                        <a :href="'#' + page.id" class="nav-link"
                           :class="{ active: currentPage === page.id }"
                           @click.prevent="navigateTo(page.id)">
                            <svg class="nav-icon" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2"
                                 stroke-linecap="round" stroke-linejoin="round"
                                 v-html="page.icon"></svg>
                            <span>{{ page.label }}</span>
                        </a>
                    </li>
                </ul>
                <div class="sidebar-footer">
                    <button class="theme-toggle" @click="toggleTheme" :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'">
                        <svg v-if="theme === 'dark'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                        </svg>
                        <svg v-else class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                        </svg>
                    </button>
                    <div class="pulse-dot" aria-hidden="true"></div>
                    <span class="status-text">System Active</span>
                </div>
            </nav>
            <main class="content" id="content">
                <div v-if="pageError" class="empty-state fade-in" style="padding: 60px 20px;">
                    <h3>Something went wrong</h3>
                    <p style="color: var(--text-secondary); margin-bottom: 16px;">
                        The <strong>{{ pageError.page }}</strong> page encountered an error.
                    </p>
                    <p style="font-size: 13px; color: var(--text-muted); font-family: monospace; background: var(--bg-surface); padding: 12px; border-radius: 6px; max-width: 600px; word-break: break-word;">
                        {{ pageError.message }}
                    </p>
                    <button class="btn" style="margin-top: 20px;" @click="pageError = null; navigateTo('dashboard')">
                        Back to Dashboard
                    </button>
                </div>
                <keep-alive v-else>
                    <component :is="currentPage + '-page'" :key="currentPage" />
                </keep-alive>
            </main>
        </template>
    `,

    computed: {
        pages() {
            return [
                { id: 'dashboard', label: 'Dashboard', icon: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>' },
                { id: 'memories', label: 'Memories', icon: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>' },
                { id: 'identity', label: 'Identity', icon: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>' },
                { id: 'reflections', label: 'Reflections', icon: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>' },
                { id: 'sessions', label: 'Sessions', icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' },
                { id: 'graph', label: 'Graph', icon: '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/><line x1="8.5" y1="7.5" x2="15.5" y2="16.5"/><line x1="15.5" y1="7.5" x2="8.5" y2="16.5"/>' },
                { id: 'threads', label: 'Threads', icon: '<path d="M4 6h16M4 12h16M4 18h10"/><circle cx="19" cy="18" r="3"/>' },
                { id: 'health', label: 'Health', icon: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>' },
                { id: 'analytics', label: 'Analytics', icon: '<path d="M18 20V10M12 20V4M6 20v-6"/>' },
                { id: 'growth', label: 'Growth', icon: '<path d="M23 6l-9.5 9.5-5-5L1 18"/><polyline points="17 6 23 6 23 12"/>' },
                { id: 'blind-spots', label: 'Blind Spots', icon: '<circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>' },
                { id: 'self-model', label: 'Self-Model', icon: '<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/><path d="M12 8v4l3 3"/>' },
            ];
        },
    },
});


// --- Legacy Page Wrapper ---
// Wraps old-style renderers (HTML string functions) as Vue components.
// Used during migration — old pages work through Vue without changes.

function legacyPage(name) {
    return {
        name: name + '-page',
        template: '<div ref="el" class="fade-in"></div>',
        setup() {
            const el = ref(null);
            onMounted(async () => {
                const renderer = App.getLegacyRenderer(name);
                const initHook = App.getLegacyRenderer(name + '_init');
                if (!renderer) {
                    el.value.innerHTML = App.emptyState('Coming Soon', 'This page is being migrated.');
                    return;
                }
                el.value.innerHTML = App.loading();
                try {
                    const html = await renderer();
                    el.value.innerHTML = html;
                    if (initHook) initHook();
                } catch (err) {
                    console.error(`Error rendering ${name}:`, err);
                    el.value.innerHTML = App.emptyState('Something went wrong', err.message);
                }
            });
            return { el };
        },
    };
}


// --- Mount on DOMContentLoaded ---
// All component/page scripts load synchronously before this fires.

document.addEventListener('DOMContentLoaded', () => {
    // Register legacy wrappers for pages not yet migrated
    const migratedPages = [
        'dashboard', 'memories', 'identity', 'reflections',
        'sessions', 'graph', 'threads', 'health', 'analytics',
        'growth', 'blind-spots', 'self-model',
    ];  // All pages migrated to Vue components
    App.PAGES.forEach(name => {
        if (!migratedPages.includes(name)) {
            megregoreApp.component(name + '-page', legacyPage(name));
        }
    });

    megregoreApp.mount('#app');
});
