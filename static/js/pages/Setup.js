/* Megregore — First-Run Setup Page (Vue Component) */

megregoreApp.component('setup-page', {
    emits: ['setup-complete'],
    setup(props, { emit }) {
        const username = ref('admin');
        const password = ref('');
        const confirm = ref('');
        const error = ref('');
        const submitting = ref(false);

        async function handleSubmit() {
            error.value = '';
            if (password.value !== confirm.value) {
                error.value = 'Passwords do not match';
                return;
            }
            if (password.value.length < 8) {
                error.value = 'Password must be at least 8 characters';
                return;
            }
            submitting.value = true;
            try {
                const res = await fetch('/api/auth/setup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: username.value,
                        password: password.value,
                    }),
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.detail || 'Setup failed');
                }
                emit('setup-complete');
            } catch (err) {
                error.value = err.message;
            } finally {
                submitting.value = false;
            }
        }

        return { username, password, confirm, error, submitting, handleSubmit };
    },
    template: `
        <div class="login-overlay">
            <div class="login-card">
                <div class="login-header">
                    <div class="logo-glyph" aria-hidden="true"></div>
                    <h1>Megregore Setup</h1>
                    <p>Create your admin account</p>
                </div>
                <div v-if="error" class="login-error">{{ error }}</div>
                <form @submit.prevent="handleSubmit" class="login-form">
                    <div class="form-group">
                        <label for="setup-username">Username</label>
                        <input id="setup-username" v-model="username" type="text"
                               autocomplete="username" required autofocus>
                    </div>
                    <div class="form-group">
                        <label for="setup-password">Password</label>
                        <input id="setup-password" v-model="password" type="password"
                               autocomplete="new-password" required minlength="8"
                               placeholder="Min 8 characters">
                    </div>
                    <div class="form-group">
                        <label for="setup-confirm">Confirm Password</label>
                        <input id="setup-confirm" v-model="confirm" type="password"
                               autocomplete="new-password" required minlength="8">
                    </div>
                    <button type="submit" class="login-btn" :disabled="submitting">
                        {{ submitting ? 'Creating account...' : 'Create Account' }}
                    </button>
                </form>
            </div>
        </div>
    `,
});
