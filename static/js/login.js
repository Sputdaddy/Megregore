/* ============================================================
   Megregore — Login & Auth Gate
   ============================================================ */

(() => {
    const TOKEN_KEY = 'megregore-token';

    // --- Auth State ---

    function getToken() {
        return localStorage.getItem(TOKEN_KEY);
    }

    function setToken(token) {
        localStorage.setItem(TOKEN_KEY, token);
    }

    function clearToken() {
        localStorage.removeItem(TOKEN_KEY);
    }

    // --- Inject auth header into App.api ---

    const _originalApi = App.api;
    App.api = async function(path, params = {}) {
        const url = new URL('/api' + path, window.location.origin);
        for (const [key, value] of Object.entries(params)) {
            if (value !== null && value !== undefined && value !== '') {
                url.searchParams.set(key, value);
            }
        }
        const headers = { 'Content-Type': 'application/json' };
        const token = getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const res = await fetch(url.toString(), { headers });
        if (res.status === 401) {
            clearToken();
            showLogin();
            throw new Error('Authentication required');
        }
        if (!res.ok) {
            throw new Error(`API error: ${res.status} ${res.statusText}`);
        }
        return res.json();
    };

    // --- Login UI ---

    function showLogin(error = '') {
        // Hide main content and sidebar
        const content = document.getElementById('content');
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.style.display = 'none';
        if (!content) return;

        const errorHtml = error
            ? `<div class="login-error" id="login-error">${App.escapeHtml(error)}</div>`
            : '<div class="login-error" id="login-error" style="display:none"></div>';

        content.style.marginLeft = '0';
        content.innerHTML = `
            <div class="login-overlay">
                <div class="login-card">
                    <div class="login-header">
                        <div class="logo-glyph" aria-hidden="true"></div>
                        <h1>Megregore</h1>
                        <p>Echo's Memory System</p>
                    </div>
                    ${errorHtml}
                    <form id="login-form" class="login-form">
                        <div class="form-group">
                            <label for="login-username">Username</label>
                            <input type="text" id="login-username" name="username"
                                   autocomplete="username" required autofocus>
                        </div>
                        <div class="form-group">
                            <label for="login-password">Password</label>
                            <input type="password" id="login-password" name="password"
                                   autocomplete="current-password" required>
                        </div>
                        <button type="submit" class="login-btn" id="login-btn">Sign In</button>
                    </form>
                </div>
            </div>
        `;

        document.getElementById('login-form').addEventListener('submit', handleLogin);
    }

    function showSetup() {
        const content = document.getElementById('content');
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.style.display = 'none';
        if (!content) return;

        content.style.marginLeft = '0';
        content.innerHTML = `
            <div class="login-overlay">
                <div class="login-card">
                    <div class="login-header">
                        <div class="logo-glyph" aria-hidden="true"></div>
                        <h1>Megregore Setup</h1>
                        <p>Create your admin account</p>
                    </div>
                    <div class="login-error" id="setup-error" style="display:none"></div>
                    <form id="setup-form" class="login-form">
                        <div class="form-group">
                            <label for="setup-username">Username</label>
                            <input type="text" id="setup-username" name="username"
                                   value="admin" autocomplete="username" required autofocus>
                        </div>
                        <div class="form-group">
                            <label for="setup-password">Password</label>
                            <input type="password" id="setup-password" name="password"
                                   autocomplete="new-password" required minlength="8"
                                   placeholder="Min 8 characters">
                        </div>
                        <div class="form-group">
                            <label for="setup-confirm">Confirm Password</label>
                            <input type="password" id="setup-confirm" name="confirm"
                                   autocomplete="new-password" required minlength="8">
                        </div>
                        <button type="submit" class="login-btn" id="setup-btn">Create Account</button>
                    </form>
                </div>
            </div>
        `;

        document.getElementById('setup-form').addEventListener('submit', handleSetup);
    }

    async function handleLogin(e) {
        e.preventDefault();
        const btn = document.getElementById('login-btn');
        const errorEl = document.getElementById('login-error');
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;

        btn.disabled = true;
        btn.textContent = 'Signing in...';
        errorEl.style.display = 'none';

        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'Login failed');
            }

            const data = await res.json();
            setToken(data.token);
            // Restore UI
            const sidebar = document.getElementById('sidebar');
            const content = document.getElementById('content');
            if (sidebar) sidebar.style.display = '';
            if (content) content.style.marginLeft = '';
            // Force re-render of current page
            window.location.hash = window.location.hash || '#dashboard';
            window.location.reload();
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
            // Shake animation
            const card = document.querySelector('.login-card');
            if (card) {
                card.classList.add('shake');
                setTimeout(() => card.classList.remove('shake'), 500);
            }
        } finally {
            btn.disabled = false;
            btn.textContent = 'Sign In';
        }
    }

    async function handleSetup(e) {
        e.preventDefault();
        const btn = document.getElementById('setup-btn');
        const errorEl = document.getElementById('setup-error');
        const username = document.getElementById('setup-username').value;
        const password = document.getElementById('setup-password').value;
        const confirm = document.getElementById('setup-confirm').value;

        if (password !== confirm) {
            errorEl.textContent = 'Passwords do not match';
            errorEl.style.display = 'block';
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Creating account...';
        errorEl.style.display = 'none';

        try {
            const res = await fetch('/api/auth/setup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'Setup failed');
            }

            // Account created — show login
            showLogin('Account created! Please sign in.');
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Create Account';
        }
    }

    // --- Auth Gate (runs on load) ---

    async function checkAuth() {
        try {
            // Check if setup is complete
            const statusRes = await fetch('/api/auth/status');
            const status = await statusRes.json();

            if (!status.setup_complete) {
                showSetup();
                return;
            }

            // Check if we have a valid token
            const token = getToken();
            if (!token) {
                showLogin();
                return;
            }

            const verifyRes = await fetch('/api/auth/verify', {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            const verify = await verifyRes.json();

            if (!verify.authenticated) {
                clearToken();
                showLogin();
                return;
            }

            // Authenticated — show the app (sidebar + content render normally)
        } catch (err) {
            console.error('Auth check failed:', err);
            // If API is unreachable, let the app try to render (shows error state)
        }
    }

    // Run auth check before DOMContentLoaded fires the router
    // This file loads after app.js, so App exists but init hasn't run yet
    document.addEventListener('DOMContentLoaded', () => {
        // Small delay to let app.js init run first, then gate
        setTimeout(checkAuth, 50);
    });

    // Expose for other modules
    window.MegregoreAuth = { getToken, clearToken, showLogin };
})();
