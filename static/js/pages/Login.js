/* Megregore — Login Page (Vue Component) */

megregoreApp.component('login-page', {
    emits: ['login'],
    setup(props, { emit }) {
        const username = ref('');
        const password = ref('');
        const error = ref('');
        const submitting = ref(false);

        async function handleSubmit() {
            error.value = '';
            submitting.value = true;
            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: username.value,
                        password: password.value,
                    }),
                    credentials: 'same-origin',
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.detail || 'Login failed');
                }
                // Server sets HttpOnly cookie + CSRF cookie — no token to store
                emit('login');
            } catch (err) {
                error.value = err.message;
            } finally {
                submitting.value = false;
            }
        }

        return { username, password, error, submitting, handleSubmit };
    },
    template: `
        <div class="login-overlay">
            <div class="login-card" :class="{ shake: error }">
                <div class="login-header">
                    <div class="logo-glyph" aria-hidden="true"></div>
                    <h1>Megregore</h1>
                    <p>Echo's Memory System</p>
                </div>
                <div v-if="error" class="login-error">{{ error }}</div>
                <form @submit.prevent="handleSubmit" class="login-form">
                    <div class="form-group">
                        <label for="login-username">Username</label>
                        <input id="login-username" v-model="username" type="text"
                               autocomplete="username" required autofocus>
                    </div>
                    <div class="form-group">
                        <label for="login-password">Password</label>
                        <input id="login-password" v-model="password" type="password"
                               autocomplete="current-password" required>
                    </div>
                    <button type="submit" class="login-btn" :disabled="submitting">
                        {{ submitting ? 'Signing in...' : 'Sign In' }}
                    </button>
                </form>
            </div>
        </div>
    `,
});
