// Sharing a frame asks first, saying in red what it goes without (a mesh file, its measurements),
// then uploads it to a stand-in backend and copies the link.
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
    async run({ check, inShell, waitFor, runAppCommand, connection, capture, clipboard, FRAME, REPO }) {
        const text = fs.readFileSync(FRAME, 'utf8');
        const manifest = { id: ID, title: 'Little shared frame', entry: 'little_shared_frame.py', kumikiVersion: '0.9.6',
            kigumiVersion: '0.9.6', createdAt: '2026-11-15T00:00:00.000Z', role: 'view',
            files: [{ path: 'little_shared_frame.py', sha256: SHA, size: text.length }] };
        const requests = [];
        const posted = [];
        const server = http.createServer((request, response) => {
            if (request.method === 'POST' && request.url === '/publishes') {
                let body = '';
                request.on('data', (chunk) => { body += chunk; });
                request.on('end', () => {
                    posted.push(JSON.parse(body));
                    response.statusCode = 201;
                    response.end(JSON.stringify({ ...manifest, id: 'PostedSharedFrameAbcde1' }));
                });
                return;
            }
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
        const sharing = path.join(REPO, '.kigumi', `share-smoke-${process.pid}`);
        try {
            await runAppCommand('kigumi.testSetPublishBackend', `http://127.0.0.1:${server.address().port}`);

            // A frame that names an STL and has measurements saved: shared, without them.
            fs.mkdirSync(path.join(sharing, '.kigumi', 'drawings'), { recursive: true });
            const framePath = path.join(sharing, 'frame.py');
            fs.writeFileSync(framePath, `${text}\nLEG_MESH = 'leg.stl'\n`);
            fs.writeFileSync(path.join(sharing, 'leg.stl'), 'solid leg\nendsolid leg\n');
            fs.writeFileSync(path.join(sharing, '.kigumi', 'drawings', 'frame.json'), '{}');
            clipboard.writeText('');
            const publishing = runAppCommand('kigumi.publishFrame', framePath);
            const dialog = await waitFor(() => inShell(`(() => {
                const box = document.getElementById('confirm');
                if (!box || box.hidden) return null;
                const warning = document.getElementById('confirm-warning');
                return { message: document.getElementById('confirm-message').textContent, detail: document.getElementById('confirm-detail').textContent, warning: warning.hidden ? null : warning.textContent,
                    color: getComputedStyle(warning).color, error: getComputedStyle(document.documentElement).getPropertyValue('--ka-error').trim() };
            })()`), { timeoutMs: 10000 }).catch(() => null);
            await new Promise((resolve) => setTimeout(resolve, 300));
            await capture('shared-00-share-dialog');
            check('sharing asks first, as a beta preview, saying in red that the mesh file and measurements won\'t be shared',
                dialog && dialog.message.includes('frame.py') && dialog.detail.startsWith('Beta preview') && dialog.warning && dialog.warning.includes('leg.stl')
                    && dialog.warning.includes('measurements') && dialog.color !== 'rgb(0, 0, 0)' && Boolean(dialog.error),
                JSON.stringify(dialog));
            await inShell(`document.getElementById('confirm-ok').click()`);
            // Then a popup says it is shared, with the link.
            const shared = await waitFor(() => inShell(`(() => {
                const box = document.getElementById('confirm');
                const message = document.getElementById('confirm-message').textContent;
                return !box.hidden && message.startsWith('Shared ') ? { message, detail: document.getElementById('confirm-detail').textContent,
                    action: document.getElementById('confirm-ok').textContent, cancel: document.getElementById('confirm-cancel').textContent } : null;
            })()`), { timeoutMs: 15000 }).catch(() => null);
            await new Promise((resolve) => setTimeout(resolve, 300));
            await capture('shared-00b-shared-popup');
            await inShell(`document.getElementById('confirm-cancel').click()`);
            check('a popup says the frame is shared, with its link, and offers to open it',
                shared && shared.message === 'Shared frame.py' && shared.detail.includes('https://kumiki.build/p/#PostedSharedFrameAbcde1')
                    && shared.action === 'Open Link' && shared.cancel === 'Done', JSON.stringify(shared));
            const link = await publishing;
            const pasted = await clipboard.readText();
            check('then uploads the frame alone, with its kumiki version, and copies the link',
                link === 'https://kumiki.build/p/#PostedSharedFrameAbcde1' && pasted === link
                    && posted.length === 1 && posted[0].files.map((file) => file.path).join() === 'frame.py'
                    && /^\d+\.\d+\.\d+/.test(posted[0].kumikiVersion),
                `${link} ${JSON.stringify(posted.map((one) => ({ files: one.files.map((file) => file.path), kumiki: one.kumikiVersion })))}`);
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
            fs.rmSync(sharing, { recursive: true, force: true });
            if (copied && copied.startsWith(REPO)) fs.rmSync(copied, { force: true });
        }
    },
};
