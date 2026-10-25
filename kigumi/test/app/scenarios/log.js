// The view's own log, in the standalone app: entries by level, and a failed build's traceback, whose
// frames open at their lines; the error overlay's button shows it. No raw Python output.

const fs = require('fs');
const path = require('path');

module.exports = {
    name: 'log',
    async run({ check, inShell, waitFor, openFrame, viewDoc, showTab, shownPage, connection, FRAME }) {
        const read = (script) => inShell(`(() => { const doc = ${viewDoc}; return ${script}; })()`);

        await openFrame(FRAME);
        await showTab('log');
        const lines = await waitFor(() => read(`doc.querySelectorAll('#log-output .log-line').length`), { timeoutMs: 20000 }).catch(() => 0);
        await read(`doc.querySelector('.log-levels [data-level="error"]').click()`);
        const errorsShown = await read(`[...doc.querySelectorAll('#log-output .log-line')].filter((line) => !line.hidden).length`);
        const oldParts = await read(`Boolean(doc.getElementById('raw-output') || doc.getElementById('log-open-output-btn'))`);
        check('the log tab lists the build, filters by level, and has no raw output or VS Code button',
            lines > 0 && errorsShown === 0 && !oldParts, `${lines} lines, ${errorsShown} errors shown, old parts ${oldParts}`);

        // A frame that fails: kept in the repository while it runs, so it builds with the repo's venv.
        const broken = path.join(path.dirname(FRAME), '_log_scenario_broken_frame.py');
        fs.writeFileSync(broken, 'from kumiki import *\n\n\ndef build_frame():\n    raise NameError("brace is not defined")\n');
        try {
            await openFrame(broken);
            const overlayButton = await waitFor(() => read(`(() => { const b = doc.getElementById('output-btn'); return b && b.style.display !== 'none'; })()`),
                { timeoutMs: 30000 }).catch(() => false);
            await showTab('tree');
            await read(`doc.getElementById('output-btn').click()`);
            const page = await shownPage();
            const traceback = await waitFor(() => read(`(() => {
                const line = [...doc.querySelectorAll('#log-output .log-error')].find((one) => one.textContent.includes('brace is not defined'));
                return line ? { links: line.querySelectorAll('.log-location').length } : null;
            })()`), { timeoutMs: 10000 }).catch(() => null);
            check("a failed build: the overlay's button shows the log, which has the traceback with links to its lines",
                overlayButton && page === 'log' && traceback && traceback.links > 0, `button ${overlayButton}, page ${page}, ${JSON.stringify(traceback)}`);

            // A traceback line for the frame file opens it in an editor tab.
            await read(`[...doc.querySelectorAll('#log-output .log-location')].find((link) => link.textContent.includes('_log_scenario_broken_frame.py')).click()`);
            const editor = await waitFor(() => {
                const active = connection().activePanel;
                return active && active.type === 'editor' ? active : null;
            }, { timeoutMs: 10000 }).catch(() => null);
            check('a traceback line opens its file in an editor', editor && editor.filePath === broken, editor && editor.filePath);
        } finally {
            fs.rmSync(broken, { force: true });
        }
    },
};
