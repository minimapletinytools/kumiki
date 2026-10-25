// The agent panel: it lists the models, offers signing in when there is no key, and a model picked
// there is kept; with a key set, it says it is using it. Its settings set the longest step. And the
// build an agent's edit runs.

module.exports = {
    name: 'agent',
    async run({ check, inShell, waitFor, capture, settings, openFrame, runAppCommand, FRAME }) {
        const agentDoc = 'document.querySelector("#slot-right iframe").contentDocument';
        const read = (script) => inShell(`(() => { const doc = ${agentDoc}; return ${script}; })()`);

        await inShell(`document.querySelector('#toggle-right').click()`);
        const models = await waitFor(() => read(`doc && doc.querySelectorAll('#model-select option').length`)
            .catch(() => 0), { timeoutMs: 10000 }).catch(() => 0);
        const note = await read(`doc.getElementById('route-note').textContent`);
        check('the agent lists the models and, with no key, offers signing in',
            models >= 4 && note.includes('Sign in') && note.includes('GitHub'), `${models} models; ${note}`);

        settings.set('agent.openrouterApiKey', 'sk-or-test');
        await read(`(() => { const select = doc.getElementById('model-select'); select.value = 'claude-haiku-4.5';
            select.dispatchEvent(new Event('change')); })()`);
        const using = await waitFor(() => read(`doc.getElementById('route-note').textContent`)
            .then((text) => (text.includes('OpenRouter key') ? text : null)), { timeoutMs: 5000 }).catch(() => '');
        check('a model picked in the panel is kept, and the panel says which key it uses',
            settings.get('agent.model') === 'claude-haiku-4.5' && Boolean(using), `${settings.get('agent.model')}; ${using}`);

        await read(`doc.getElementById('btn-settings').click()`);
        const shown = await read(`doc.getElementById('setting-output-limit').value`);
        await read(`(() => { const select = doc.getElementById('setting-output-limit'); select.value = '32000';
            select.dispatchEvent(new Event('change')); })()`);
        const limit = await waitFor(() => settings.get('agent.maxOutputTokens') === 32000, { timeoutMs: 5000 }).catch(() => false);
        await capture('agent-settings');
        await read(`doc.getElementById('btn-settings').click()`);
        settings.set('agent.maxOutputTokens', 8000);
        check('the settings menu sets the longest step', shown === '8000' && limit, `shown ${shown}, now ${settings.get('agent.maxOutputTokens')}`);

        // What an edit by the agent runs: the view's file built as it is, and that build's problems.
        await openFrame(FRAME);
        const report = await runAppCommand('kigumi.automationBuildReport', { filePath: FRAME, graceMs: 0 });
        check('a view\'s file builds on request, reporting that build\'s problems',
            report && report.ok === true && Array.isArray(report.entries) && report.entries.length === 0, JSON.stringify(report).slice(0, 200));
    },
};
