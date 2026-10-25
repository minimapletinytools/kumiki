// The app's one log, in its Log tab: a view has no log of its own, and its "view log" button opens
// the Log tab showing that view's file, with a failed build's traceback whose frames open their lines.
// A failed build's overlay also goes straight to the line that raised.

const fs = require('fs');
const path = require('path');

module.exports = {
    name: 'log',
    async run({ check, inShell, waitFor, capture, openFrame, viewDoc, connection, FRAME }) {
        const read = (script) => inShell(`(() => { const doc = ${viewDoc}; return ${script}; })()`);

        await openFrame(FRAME);
        const idleButtons = await read(`Boolean(doc.getElementById('output-btn'))`);
        check('a view that built shows no error buttons', !idleButtons, `buttons ${idleButtons}`);
        const viewLog = await read(`Boolean(doc.querySelector('.vsb-tab[data-tab="log"]') || doc.getElementById('log-panel-box'))`);
        check('a view has no Log tab of its own', !viewLog, `view log ${viewLog}`);

        // A frame that fails: kept in the repository while it runs, so it builds with the repo's venv.
        const broken = path.join(path.dirname(FRAME), '_log_scenario_broken_frame.py');
        const name = path.basename(broken);
        fs.writeFileSync(broken, 'from kumiki import *\n\n\ndef build_frame():\n    print("probe 42")\n    raise NameError("brace is not defined")\n');
        try {
            await openFrame(broken);
            const button = await waitFor(() => read(`Boolean(doc.getElementById('output-btn') && doc.getElementById('go-to-error-btn'))`),
                { timeoutMs: 30000 }).catch(() => false);
            await new Promise((resolve) => setTimeout(resolve, 1500));
            await capture('log-error-overlay');
            // The overlay's "go to error" opens the frame at the line that raised.
            const viewTab = connection().activePanel;
            await read(`doc.getElementById('go-to-error-btn').click()`);
            const atError = await waitFor(() => {
                const active = connection().activePanel;
                return active && active.type === 'editor' ? active : null;
            }, { timeoutMs: 10000 }).catch(() => null);
            check('a failed build\'s "go to error" opens its file', atError && atError.filePath === broken, atError && atError.filePath);
            atError.dispose();
            viewTab.reveal();

            await read(`doc.getElementById('output-btn').click()`);
            const logTab = await waitFor(() => {
                const active = connection().activePanel;
                return active && active.type === 'log' ? active : null;
            }, { timeoutMs: 10000 }).catch(() => null);
            const shown = await waitFor(() => read(`(() => {
                const lines = [...doc.querySelectorAll('#entries .log-line')].filter((line) => !line.hidden);
                const error = lines.find((line) => line.classList.contains('log-error') && line.textContent.includes('brace is not defined'));
                const printed = lines.some((line) => line.textContent.includes('[python] probe 42'));
                return error ? { source: doc.getElementById('source').value, links: error.querySelectorAll('.log-location').length, printed } : null;
            })()`), { timeoutMs: 10000 }).catch(() => null);
            check("the view's log button opens the Log tab showing its file: what it printed, and the traceback linked to its lines",
                button && logTab && shown && shown.source === name && shown.links > 0 && shown.printed,
                `button ${button}, log tab ${Boolean(logTab)}, ${JSON.stringify(shown)}`);

            await read(`doc.querySelector('#levels [data-level="error"]').click()`);
            await read(`(() => { const select = doc.getElementById('source'); select.value = ''; select.dispatchEvent(new Event('change')); })()`);
            const levels = await read(`[...doc.querySelectorAll('#entries .log-line')].filter((line) => !line.hidden)
                .every((line) => line.classList.contains('log-error'))`);
            check('the Log tab filters by level, across everything', levels, `only errors ${levels}`);

            // A traceback line for the frame file opens it in an editor tab.
            await read(`[...doc.querySelectorAll('#entries .log-location')].find((link) => link.textContent.includes('${name}')).click()`);
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
