// A shared frame's link opens the frame in a viewer, from a stand-in backend: it is listed under
// Shared with the kumiki version it was built with, its source opens read-only, and it can be
// copied into the project or taken off the list.

const fs = require('fs');
const http = require('http');
const path = require('path');

const ID = 'TestSharedFrameAbcdef1';
const SHA = 'f'.repeat(64);

module.exports = {
    name: 'shared',
    async run({ check, inShell, waitFor, runAppCommand, connection, capture, FRAME, REPO }) {
        const text = fs.readFileSync(FRAME, 'utf8');
        const manifest = { id: ID, title: 'Little shared frame', entry: 'little_shared_frame.py', kumikiVersion: '0.9.6',
            kigumiVersion: '0.9.6', createdAt: '2026-11-15T00:00:00.000Z', role: 'view',
            files: [{ path: 'little_shared_frame.py', sha256: SHA, size: text.length }] };
        const requests = [];
        const server = http.createServer((request, response) => {
            requests.push(request.url);
            if (request.url === `/publishes/${ID}`) response.end(JSON.stringify(manifest));
            else if (request.url === `/publishes/${ID}/files/${SHA}`) response.end(text);
            else { response.statusCode = 404; response.end('{}'); }
        });
        await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
        const sidebarRow = (key) => inShell(`(() => {
            const doc = document.querySelector('#slot-left iframe')?.contentDocument;
            const row = doc && doc.querySelector('.ks-row[data-key="' + CSS.escape(${JSON.stringify(key)}) + '"]');
            return row ? row.textContent.replace(/\\s+/g, ' ').trim() : null;
        })()`);
        let copied = null;
        try {
            await runAppCommand('kigumi.testSetPublishBackend', `http://127.0.0.1:${server.address().port}`);
            const entryPath = await runAppCommand('kigumi.openPublish', `https://kumiki.build/p/#${ID}`);
            check('a share link downloads the frame', typeof entryPath === 'string' && fs.readFileSync(entryPath, 'utf8') === text,
                `${entryPath} ${JSON.stringify(requests)}`);
            const drew = await waitFor(() => inShell(`(() => {
                const frame = document.querySelector('#slot-center iframe:not([hidden])');
                return !!(frame && frame.contentDocument && frame.contentDocument.querySelector('canvas'));
            })()`), { timeoutMs: 60000 }).then(() => true, () => false);
            const shown = connection().activePanel && connection().activePanel.filePath;
            check('and opens it in a viewer', drew && shown && fs.realpathSync(shown) === fs.realpathSync(entryPath), `${drew} ${shown}`);
            const row = await waitFor(() => sidebarRow(`shared:${ID}`), { timeoutMs: 5000 }).catch(() => null);
            check('the explorer lists it under Shared, with the kumiki version it was built with',
                row && row.includes('Little shared frame') && row.includes('kumiki 0.9.6'), row);
            await capture('shared-01-opened');

            await runAppCommand('kigumi.openFileSource', entryPath);
            const readOnly = await waitFor(() => inShell(`(() => {
                const frame = document.querySelector('#slot-center iframe:not([hidden])');
                const win = frame && frame.contentWindow;
                const editor = win && win.monaco && win.monaco.editor.getEditors()[0];
                if (!editor) return null;
                return editor.getOption(win.monaco.editor.EditorOption.readOnly) ? 'read-only' : 'editable';
            })()`), { timeoutMs: 15000 }).catch(() => null);
            check('its source opens read-only', readOnly === 'read-only', String(readOnly));

            await runAppCommand('kigumi.openPublish', ID);
            check('opening it again uses the copy already downloaded', requests.length === 2, JSON.stringify(requests));

            copied = await runAppCommand('kigumi.copyPublishToProject', { data: { publishId: ID } });
            check('copying it to the project makes a file there that can be changed',
                typeof copied === 'string' && copied.startsWith(REPO) && fs.readFileSync(copied, 'utf8') === text, copied);

            await runAppCommand('kigumi.removePublish', { data: { publishId: ID } });
            const gone = await waitFor(async () => (await sidebarRow(`shared:${ID}`)) === null, { timeoutMs: 5000 }).then(() => true, () => false);
            check('removing it takes it off Shared and deletes the download', gone && !fs.existsSync(entryPath));
        } finally {
            await runAppCommand('kigumi.testSetPublishBackend', null);
            server.close();
            if (copied && copied.startsWith(REPO)) fs.rmSync(copied, { force: true });
        }
    },
};
