/* ============================================================
   Megregore — SPA Router & Shared Utilities
   ============================================================ */

const App = (() => {

    // --- Configuration ---
    const API_BASE = '/api';
    const PAGES = ['dashboard', 'memories', 'identity', 'reflections', 'sessions', 'graph', 'analytics', 'threads'];

    // --- API Helper ---
    async function api(path, params = {}) {
        const url = new URL(API_BASE + path, window.location.origin);
        for (const [key, value] of Object.entries(params)) {
            if (value !== null && value !== undefined && value !== '') {
                url.searchParams.set(key, value);
            }
        }
        const res = await fetch(url.toString());
        if (!res.ok) {
            throw new Error(`API error: ${res.status} ${res.statusText}`);
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

        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const month = months[date.getMonth()];
        const day = date.getDate();
        const year = date.getFullYear();
        const currentYear = now.getFullYear();

        if (year === currentYear) {
            return `${month} ${day}`;
        }
        return `${month} ${day}, ${year}`;
    }

    function formatDateFull(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }


    // --- Text Utilities ---
    function truncateText(text, maxLen = 200) {
        if (!text || text.length <= maxLen) return text || '';
        return text.substring(0, maxLen).trimEnd() + '...';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }


    // --- Badge / Pill Generators ---
    function typeBadge(memoryType) {
        const t = (memoryType || 'experience').toLowerCase();
        return `<span class="type-badge ${t}">${escapeHtml(t)}</span>`;
    }

    function insightBadge(insightType) {
        const t = (insightType || 'pattern').toLowerCase();
        return `<span class="insight-badge ${t}">${escapeHtml(t)}</span>`;
    }

    function importanceDots(value) {
        const v = Math.max(1, Math.min(10, value || 5));
        let dots = '';
        for (let i = 1; i <= 10; i++) {
            dots += `<span class="dot ${i <= v ? 'filled' : ''}"></span>`;
        }
        return `<span class="importance-dots" title="Importance: ${v}/10">${dots}</span>`;
    }

    function importanceBar(value) {
        const v = Math.max(1, Math.min(10, value || 5));
        const pct = v * 10;
        return `<span class="importance-bar">
            <span class="importance-bar-track"><span class="importance-bar-fill" style="width:${pct}%"></span></span>
            <span>${v}</span>
        </span>`;
    }

    function emotionalIndicator(weight) {
        const w = weight || 0;
        let cls, label;
        if (w > 0.05) {
            cls = 'positive';
            label = '+' + w.toFixed(2);
        } else if (w < -0.05) {
            cls = 'negative';
            label = w.toFixed(2);
        } else {
            cls = 'neutral';
            label = '0.00';
        }
        return `<span class="emotional-indicator ${cls}">
            <span class="emotional-dot ${cls}"></span>
            ${label}
        </span>`;
    }

    function activationBar(level) {
        const v = Math.max(0, Math.min(1, level || 0));
        const pct = Math.round(v * 100);
        let cls = 'high';
        if (v < 0.3) cls = 'low';
        else if (v < 0.7) cls = 'mid';
        return `<span class="activation-bar" title="Activation: ${v.toFixed(2)}">
            <span class="activation-bar-track"><span class="activation-bar-fill ${cls}" style="width:${pct}%"></span></span>
            <span class="activation-label">${v.toFixed(2)}</span>
        </span>`;
    }

    function tagPills(tags) {
        if (!tags || !tags.length) return '';
        return `<span class="tag-pills">${tags.map(t =>
            `<span class="tag-pill">${escapeHtml(t)}</span>`
        ).join('')}</span>`;
    }


    // --- Markdown-lite Renderer (for identity docs) ---
    function renderMarkdown(text) {
        if (!text) return '';
        let html = escapeHtml(text);

        // Headers
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

        // Bold and italic
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

        // Inline code
        html = html.replace(/`(.+?)`/g, '<code>$1</code>');

        // Unordered lists
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        // Wrap consecutive <li> in <ul>
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

        // Paragraphs — wrap remaining lines
        html = html.split('\n\n').map(block => {
            block = block.trim();
            if (!block) return '';
            if (block.startsWith('<h') || block.startsWith('<ul') || block.startsWith('<ol')) return block;
            // Don't wrap if it's already wrapped
            if (block.startsWith('<')) return block;
            return `<p>${block}</p>`;
        }).join('\n');

        // Clean up stray single newlines inside paragraphs
        html = html.replace(/(?<!\n)\n(?!\n)/g, '<br>');

        return html;
    }


    // --- Empty State ---
    function emptyState(title, message) {
        return `<div class="empty-state fade-in">
            <div class="empty-glyph">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M8 12h8M12 8v8"/>
                </svg>
            </div>
            <h3>${escapeHtml(title)}</h3>
            <p>${escapeHtml(message)}</p>
        </div>`;
    }

    // --- Loading State ---
    function loading() {
        return '<div class="loading"><div class="spinner"></div></div>';
    }


    // --- Router ---
    let currentPage = null;

    const pageRenderers = {};

    function registerPage(name, renderer) {
        pageRenderers[name] = renderer;
    }

    function getPage() {
        const hash = window.location.hash.replace('#', '') || 'dashboard';
        return PAGES.includes(hash) ? hash : 'dashboard';
    }

    function navigate(page) {
        if (!PAGES.includes(page)) page = 'dashboard';
        window.location.hash = '#' + page;
    }

    async function renderPage() {
        const page = getPage();
        if (page === currentPage) return;
        currentPage = page;

        // Update nav active state
        document.querySelectorAll('.nav-link').forEach(link => {
            const linkPage = link.getAttribute('data-page');
            link.classList.toggle('active', linkPage === page);
        });

        const content = document.getElementById('content');
        if (!content) return;

        // Show loading
        content.innerHTML = loading();

        // Render the page
        const renderer = pageRenderers[page];
        if (renderer) {
            try {
                const html = await renderer();
                content.innerHTML = html;
                // Run any post-render hooks
                const hook = pageRenderers[page + '_init'];
                if (hook) hook();
            } catch (err) {
                console.error(`Error rendering ${page}:`, err);
                content.innerHTML = emptyState(
                    'Something went wrong',
                    'Could not load this page. Is the API server running on localhost:3000?'
                );
            }
        } else {
            content.innerHTML = emptyState('Page not found', 'This page does not exist.');
        }
    }


    // --- Init ---
    function init() {
        window.addEventListener('hashchange', () => {
            currentPage = null; // Force re-render on hash change
            renderPage();
        });

        // Handle nav clicks
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.getAttribute('data-page');
                navigate(page);
            });
        });

        // Initial render
        renderPage();
    }

    document.addEventListener('DOMContentLoaded', init);


    // --- Public API ---
    return {
        api,
        formatDate,
        formatDateFull,
        truncateText,
        escapeHtml,
        typeBadge,
        insightBadge,
        importanceDots,
        importanceBar,
        emotionalIndicator,
        tagPills,
        activationBar,
        renderMarkdown,
        emptyState,
        loading,
        registerPage,
        navigate,
    };

})();
