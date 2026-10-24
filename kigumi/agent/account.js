/**
 * The Kigumi account: signing in with GitHub or Google (Supabase, PKCE), the access token model
 * requests to the backend carry, and the balance. Host-neutral: the desktop app gives it encrypted
 * file storage and the `kigumi://auth` link; a web page would give it localStorage and its own URL.
 */

const { createClient } = require('@supabase/supabase-js');

/**
 * @param {object} options
 * @param {string} options.supabaseUrl
 * @param {string} options.supabaseKey   the project's publishable (anon) key
 * @param {string} options.backendUrl    the Worker
 * @param {object} [options.storage]     getItem / setItem / removeItem, sync or async
 * @param {string} options.redirectTo    where sign-in comes back to, e.g. kigumi://auth
 * @param {(url: string) => Promise<void>|void} options.openExternal  opens the sign-in page
 * @param {typeof fetch} [options.fetch]
 * @param {() => void} [options.onChange]  signed in or out, or the balance changed
 */
function createAccount({ supabaseUrl, supabaseKey, backendUrl, storage, redirectTo, openExternal,
    fetch: fetcher = (...args) => fetch(...args), onChange = () => {} }) {
    const configured = Boolean(supabaseUrl && supabaseKey && backendUrl);
    let user = null;
    let balanceUsd = null;

    const client = configured ? createClient(supabaseUrl, supabaseKey, {
        auth: { flowType: 'pkce', storage, persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
        global: { fetch: fetcher },
    }) : null;

    async function accessToken() {
        if (!client) return null;
        const { data } = await client.auth.getSession();
        return (data.session && data.session.access_token) || null;
    }

    async function refreshBalance() {
        const token = await accessToken();
        if (!token) return;
        const response = await fetcher(`${backendUrl.replace(/\/$/, '')}/account`, { headers: { Authorization: `Bearer ${token}` } });
        if (response.ok) {
            balanceUsd = (await response.json()).balanceUsd;
            onChange();
        }
    }

    if (client) {
        client.auth.onAuthStateChange((_event, session) => {
            const next = (session && session.user) || null;
            const changed = (next && next.id) !== (user && user.id);
            user = next;
            if (!user) balanceUsd = null;
            if (changed) {
                onChange();
                // Not inside the callback: Supabase holds a lock while it runs.
                if (user) setTimeout(() => void refreshBalance().catch(() => {}), 0);
            }
        });
    }

    return {
        get configured() {
            return configured;
        },

        /** For the panel. */
        state() {
            return { configured, signedIn: Boolean(user), email: (user && user.email) || null, balanceUsd };
        },

        /** Where model requests go when signed in, for agent/models.js routeModel; else null. */
        backend() {
            return user ? { url: backendUrl } : null;
        },

        /** Open the provider's sign-in page; it comes back to `redirectTo` with a code (completeSignIn). */
        async signIn(provider) {
            if (!client) throw new Error('Signing in is not set up in this build.');
            const { data, error } = await client.auth.signInWithOAuth({ provider, options: { redirectTo, skipBrowserRedirect: true } });
            if (error) throw error;
            await openExternal(data.url);
        },

        /** Finish signing in from the URL sign-in came back to. */
        async completeSignIn(url) {
            const params = new URL(url).searchParams;
            if (params.get('error')) throw new Error(params.get('error_description') || params.get('error'));
            const { error } = await client.auth.exchangeCodeForSession(params.get('code') || '');
            if (error) throw error;
        },

        async signOut() {
            if (client) await client.auth.signOut({ scope: 'local' });
        },

        refreshBalance,

        /** fetch, carrying a current access token: one per model request, so a long turn never sends a stale one. */
        async fetchWithToken(input, init = {}) {
            const headers = new Headers(init.headers);
            headers.set('Authorization', `Bearer ${await accessToken()}`);
            return fetcher(input, { ...init, headers });
        },
    };
}

module.exports = { createAccount };
