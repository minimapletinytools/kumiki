const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { PageStore } = require('../app-shell/page-store');
const { webviewDir } = require('../webview-html');
const { createWebServer, browserPage } = require('../hosts/web/server');

test('allows template style attributes without relaxing the script policy', () => {
    const html = '<head><meta content="script-src \'nonce-abc123\'; style-src http://127.0.0.1:7346;"><script nonce="abc123"></script>';
    expect(browserPage(html)).toContain('style-src http://127.0.0.1:7346; style-src-attr \'unsafe-inline\';');
    expect(browserPage(html)).toContain('script-src \'nonce-abc123\';');
});

describe('browser host HTTP boundary', () => {
    let web;
    let origin;
    let receive;
    let controller;

    beforeEach(async () => {
        receive = jest.fn();
        web = createWebServer({ pages: new PageStore({ origin: '', webviewDir }), onMessage: receive });
        origin = await web.listen(0);
        controller = new AbortController();
    });
    afterEach(async () => {
        controller.abort();
        await web.close();
    });

    test('serves the shared shell with the browser transport and CSP', async () => {
        const response = await fetch(origin);
        expect(response.status).toBe(200);
        const html = await response.text();
        expect(html).toContain('<base href="/webview/shell/">');
        expect(html).toContain('connect-src \'self\'');
        expect(html.indexOf('/web-host/transport.js')).toBeLessThan(html.indexOf('src="shell.js"'));
        expect((await fetch(`${origin}/webview/vendor/lit.min.js`)).status).toBe(200);
    });

    test('rejects foreign origins, DNS rebinding hosts, and unauthenticated messages', async () => {
        expect((await fetch(origin, { headers: { Origin: 'https://example.com' } })).status).toBe(403);
        const reboundStatus = await new Promise((resolve) => {
            http.get(origin, { headers: { Host: 'example.com' } }, (response) => {
                response.resume();
                resolve(response.statusCode);
            });
        });
        expect(reboundStatus).toBe(403);
        expect((await fetch(`${origin}/message`, {
            method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: '{}',
        })).status).toBe(403);
        expect(receive).not.toHaveBeenCalled();
    });

    test('delivers messages in both directions and rejects a second controlling tab', async () => {
        const response = await fetch(`${origin}/events?client=first`, { signal: controller.signal });
        const reader = response.body.getReader();
        await reader.read();
        expect((await fetch(`${origin}/events?client=second`)).status).toBe(409);
        web.send({ type: 'shell:state', panels: [] });
        expect(new TextDecoder().decode((await reader.read()).value)).toContain('"type":"shell:state"');
        const post = (body, extra = {}) => fetch(`${origin}/message`, {
            method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json', 'X-Kigumi-Client': 'first', ...extra }, body,
        });
        expect((await post('{')).status).toBe(400);
        expect((await post('{}')).status).toBe(400);
        expect((await post('{"type":"shell:ready"}', { 'X-Kigumi-Client': 'second' })).status).toBe(403);
        expect((await post('{"type":"shell:ready"}')).status).toBe(204);
        expect(receive).toHaveBeenCalledWith({ type: 'shell:ready' });
        expect((await post(JSON.stringify({ type: 'panel:message', data: 'x'.repeat(2 * 1024 * 1024) }))).status).toBe(413);
    });

    test('does not expose repository files or symlinks outside webview assets', async () => {
        expect((await fetch(`${origin}/webview/%2e%2e%2fpackage.json`)).status).toBe(404);
        expect((await fetch(`${origin}/web-host/server.js`)).status).toBe(404);
        const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-web-'));
        const link = path.join(webviewDir, `test-link-${process.pid}`);
        try {
            fs.writeFileSync(path.join(temp, 'secret.txt'), 'private');
            fs.symlinkSync(path.join(temp, 'secret.txt'), link);
            expect((await fetch(`${origin}/webview/${path.basename(link)}`)).status).toBe(404);
        } finally {
            fs.rmSync(link, { force: true });
            fs.rmSync(temp, { recursive: true, force: true });
        }
    });
});
