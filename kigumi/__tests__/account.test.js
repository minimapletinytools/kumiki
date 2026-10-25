const { createAccount } = require('../agent/account');
const { SecureStorage } = require('../hosts/electron/secure-storage');
const fs = require('fs');
const os = require('os');
const path = require('path');

const SUPABASE = 'https://project.supabase.test';
const BACKEND = 'https://api.kigumi.test';

/** Supabase's auth server and Kigumi's backend, as much as signing in and the balance use. */
function fakeServers() {
    const calls = [];
    const session = (token) => ({
        access_token: token, token_type: 'bearer', expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600,
        refresh_token: `refresh-${token}`, user: { id: 'user-1', email: 'maple@example.com', aud: 'authenticated' },
    });
    const fetch = async (input, init = {}) => {
        const url = new URL(String(input));
        const body = init.body ? JSON.parse(init.body) : null;
        calls.push({ url, body, headers: new Headers(init.headers) });
        if (url.origin === SUPABASE && url.pathname === '/auth/v1/token' && url.searchParams.get('grant_type') === 'pkce') {
            return body.auth_code === 'good-code' && body.code_verifier
                ? Response.json(session('access-1'))
                : Response.json({ error: 'invalid_grant', error_description: 'bad code' }, { status: 400 });
        }
        if (url.origin === SUPABASE && url.pathname === '/auth/v1/logout') {
            return new Response(null, { status: 204 });
        }
        if (url.origin === BACKEND && url.pathname === '/account') {
            return Response.json({ balanceUsd: 0.97, markup: 1.4, usage: [] });
        }
        return Response.json({ echoed: true });
    };
    return { fetch, calls };
}

function memoryStorage() {
    const values = new Map();
    return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

function account(overrides = {}) {
    const servers = fakeServers();
    const opened = [];
    const changes = [];
    const made = createAccount({
        supabaseUrl: SUPABASE, supabaseKey: 'publishable-key', backendUrl: BACKEND,
        storage: memoryStorage(), redirectTo: 'kigumi://auth',
        openExternal: (url) => opened.push(url), fetch: servers.fetch, onChange: () => changes.push(made.state()),
        ...overrides,
    });
    return { account: made, servers, opened, changes };
}

describe('the Kigumi account', () => {
    test('without a backend configured it offers nothing', () => {
        const unconfigured = createAccount({ supabaseUrl: '', supabaseKey: '', backendUrl: '', redirectTo: 'kigumi://auth', openExternal: () => {} });
        expect(unconfigured.state()).toEqual({ configured: false, signedIn: false, email: null, balanceUsd: null, markup: null });
        expect(unconfigured.backend()).toBeNull();
    });

    test('signing in opens the provider in the browser, coming back to kigumi://auth with a code challenge', async () => {
        const { account: signedOut, opened } = account();
        await signedOut.signIn('github');

        const url = new URL(opened[0]);
        expect(url.origin + url.pathname).toBe(`${SUPABASE}/auth/v1/authorize`);
        expect(url.searchParams.get('provider')).toBe('github');
        expect(url.searchParams.get('redirect_to')).toBe('kigumi://auth');
        expect(url.searchParams.get('code_challenge')).toBeTruthy();
    });

    test('the code coming back signs in; requests then carry the token, and the balance is fetched', async () => {
        const { account: signingIn, servers, changes } = account();
        await signingIn.signIn('github');
        await signingIn.completeSignIn('kigumi://auth?code=good-code');
        await settle();

        expect(signingIn.state()).toEqual({ configured: true, signedIn: true, email: 'maple@example.com', balanceUsd: 0.97, markup: 1.4 });
        expect(signingIn.backend()).toEqual({ url: BACKEND });
        expect(changes.length).toBeGreaterThan(0);

        await signingIn.fetchWithToken(`${BACKEND}/v1/chat/completions`, { method: 'POST', headers: { Authorization: 'Bearer kigumi-account' } });
        expect(servers.calls.at(-1).headers.get('Authorization')).toBe('Bearer access-1');
    });

    test('a refused code, or an error coming back, says so', async () => {
        const { account: signingIn } = account();
        await signingIn.signIn('google');
        await expect(signingIn.completeSignIn('kigumi://auth?code=bad')).rejects.toThrow();
        await expect(signingIn.completeSignIn('kigumi://auth?error=access_denied&error_description=Denied')).rejects.toThrow('Denied');
        expect(signingIn.state().signedIn).toBe(false);
    });

    test('signing out forgets the session', async () => {
        const { account: signedIn } = account();
        await signedIn.signIn('github');
        await signedIn.completeSignIn('kigumi://auth?code=good-code');
        await signedIn.signOut();
        await settle();
        expect(signedIn.state().signedIn).toBe(false);
        expect(signedIn.backend()).toBeNull();
    });
});

describe('the sign-in storage', () => {
    let folder;
    beforeEach(() => { folder = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-account-')); });
    afterEach(() => fs.rmSync(folder, { recursive: true, force: true }));

    const reversing = {
        isEncryptionAvailable: () => true,
        encryptString: (text) => Buffer.from([...text].reverse().join('')),
        decryptString: (buffer) => [...buffer.toString()].reverse().join(''),
    };

    test('is kept encrypted on disk, and read back', () => {
        const file = path.join(folder, 'account');
        new SecureStorage(file, reversing).setItem('session', '{"token":"secret"}');
        expect(fs.readFileSync(file, 'utf8')).not.toContain('secret');
        expect(new SecureStorage(file, reversing).getItem('session')).toBe('{"token":"secret"}');
    });

    test('with no OS encryption, nothing is written', () => {
        const file = path.join(folder, 'account');
        new SecureStorage(file, { isEncryptionAvailable: () => false }).setItem('session', 'x');
        expect(fs.existsSync(file)).toBe(false);
    });
});
